from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from app.core.prompt_versioning import prompt_metadata
from app.core.logging import logger
from app.events.bus import event_bus
from app.services.agent_actions import (
    create_grocery_list_from_message,
    create_meal_plan_from_message,
)
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.services.openai_utils import (
    is_openai_model_not_found_error,
    openai_chat_model_candidates,
)
from app.services.weather_service import weather_service
from app.services.activity_search_service import activity_search_service
from app.services.recipe_search_service import recipe_search_service
from app.services.web_search_service import web_search_service
from app.services.privacy import redact_pii
import operator
import re
from datetime import datetime


def _build_google_llm(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.google_api_key,
        temperature=0.3,
    )


def _build_openai_llm(model_name: Optional[str] = None):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_name or settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.3,
    )


def _build_llm():
    if settings.openai_api_key:
        return _build_openai_llm()
    elif settings.google_api_key:
        return _build_google_llm(settings.google_model)
    return None


def _google_model_fallbacks(current_model: str) -> list[str]:
    candidates = [
        current_model,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ]
    seen = set()
    ordered = []
    for model in candidates:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)
    return ordered


def _is_missing_google_model_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "model" in text
        and (
            "not found" in text
            or "not supported" in text
            or "invalid" in text
            or "generatecontent" in text
        )
    )


def _build_google_or_openai_fallback(provider: str, model_name: Optional[str] = None):
    if provider == "openai" and settings.openai_api_key:
        return _build_openai_llm(model_name or settings.openai_model)
    if provider == "google" and settings.google_api_key:
        return _build_google_llm(model_name or settings.google_model)
    return None


def _is_create_request(message: str, keywords: List[str]) -> bool:
    lower = message.lower()
    action_words = ("create", "make", "generate", "build", "set up", "prepare", "plan")
    return any(word in lower for word in action_words) and any(keyword in lower for keyword in keywords)


def _strip_trailing_time_words(value: str) -> str:
    cleaned = value.strip(" .,!?:;")
    for suffix in [
        " today",
        " tomorrow",
        " this week",
        " next week",
        " this weekend",
        " next weekend",
        " weekend",
        " tonight",
        " now",
    ]:
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    return cleaned.strip(" .,!?:;")


def _strip_trailing_date_clause(value: str) -> str:
    cleaned = value.strip(" .,!?:;")
    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\s+\d{4}\b",
        r"\b[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    ]
    earliest = None
    for pattern in date_patterns:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match and (earliest is None or match.start() < earliest):
            earliest = match.start()
    if earliest is not None:
        cleaned = cleaned[:earliest]
    return cleaned.strip(" .,!?:;")


def _extract_location_from_message(message: str) -> Optional[str]:
    text = message.strip()
    patterns = [
        r"(?:weather|forecast|events?|things to do|activities|family events?|kids activities?)\s+(?:in|near|for)\s+(.*)$",
        r"(?:in|near|for)\s+([A-Za-z0-9 ,'-]+)$",
    ]
    lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lower, re.IGNORECASE)
        if match:
            value = text[match.start(1): match.end(1)]
            value = _strip_trailing_date_clause(value)
            return _strip_trailing_time_words(value)
    return None


def _extract_recipe_query(message: str) -> str:
    text = message.strip()
    patterns = [
        r"^(?:recipe|recipes)\s+(?:for|of)\s+(.*)$",
        r"^(?:find|search|show|suggest)\s+(?:a\s+)?(?:recipe|recipes)\s+(?:for|of)?\s*(.*)$",
        r"^(?:how do i make|how to make|cook|bake)\s+(.*)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, text, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return text


def _matches_any(text: str, phrases: List[str]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def _activity_source_domains(message: str) -> Optional[List[str]]:
    if not _matches_any(
        message,
        [
            "kids",
            "children",
            "family",
            "families",
            "family-friendly",
            "family friendly",
            "school holiday",
            "school holidays",
            "holiday activities",
            "days out",
        ],
    ):
        return None
    return settings.activity_search_source_domains


def _format_activity_reply(
    location: Optional[str],
    results: List[Dict[str, Any]],
    pages: Optional[List[Dict[str, Any]]] = None,
) -> str:
    area = location or "your area"
    if not results:
        if pages:
            lines = [f"No structured local family-friendly activities were found for {area}, but these pages may be helpful:"]
            for idx, item in enumerate(pages[:8], start=1):
                title = item.get("page_title") or item.get("title") or "Untitled page"
                url = item.get("url") or ""
                snippet = item.get("page_description") or item.get("page_excerpt") or item.get("snippet") or "not listed"
                source = item.get("domain") or "not listed"
                lines.append(
                    f"{idx}. {title} - Source: {source} - Link: {url or 'not listed'} - Snippet: {snippet}"
                )
            return "\n".join(lines)
        return f"No local family-friendly activities were found for {area}."

    lines = [f"Family-friendly activities near {area}:"]
    for idx, item in enumerate(results[:8], start=1):
        title = item.get("title") or item.get("name") or "Untitled activity"
        venue = item.get("venue") or {}
        when = " ".join(part for part in [item.get("date"), item.get("time")] if part)
        place = ", ".join(
            part for part in [
                venue.get("name"),
                venue.get("city"),
                venue.get("country"),
            ] if part
        )
        details = [
            f"Cost: {item.get('cost')}" if item.get("cost") else None,
            f"Transport: {item.get('transport')}" if item.get("transport") else None,
            f"Time taken: {item.get('time_taken')}" if item.get("time_taken") else None,
            f"Source: {item.get('source')}" if item.get("source") else None,
            f"Link: {item.get('url')}" if item.get("url") else None,
        ]
        detail_text = " | ".join(part for part in details if part)
        lines.append(
            f"{idx}. {title}"
            f"{f' - {when}' if when else ''}"
            f"{f' - {place}' if place else ''}"
            f"{f' - {detail_text}' if detail_text else ''}"
        )
    return "\n".join(lines)


def _format_web_search_reply(query: str, search_results: Dict[str, Any]) -> str:
    results = search_results.get("pages") or search_results.get("results") or []
    lines = [f"Web search results for: {search_results.get('query', query)}"]
    if not results:
        lines.append("No web results were found.")
        return "\n".join(lines)

    for idx, item in enumerate(results[:8], start=1):
        title = item.get("page_title") or item.get("title") or "Untitled"
        url = item.get("url") or ""
        snippet = item.get("page_description") or item.get("snippet") or item.get("page_excerpt") or ""
        lines.append(
            f"{idx}. {title}"
            f"{f' - {url}' if url else ''}"
            f"{f' - {snippet}' if snippet else ''}"
        )
    return "\n".join(lines)


def _format_weather_reply(location: str, weather: Dict[str, Any]) -> str:
    resolved = (weather.get("location") or {}).get("name") or location or "your area"
    lines = [f"Weather for {resolved}"]
    current = weather.get("current") or {}
    if current:
        lines.append(
            f"Current: {current.get('temperature')}°C, {current.get('summary')}, "
            f"wind {current.get('wind_speed')} km/h"
        )
    daily = weather.get("daily") or []
    if daily:
        lines.append("Forecast:")
        for day in daily[:5]:
            lines.append(
                f"- {day.get('date')}: {day.get('summary')} | "
                f"{day.get('temperature_min')}°C to {day.get('temperature_max')}°C"
            )
    return "\n".join(lines)


_INVENTORY_RECIPE_HINTS = [
    "use what i have",
    "use what we have",
    "available ingredients",
    "available in the pantry",
    "available in the grocery",
    "ingredients i have",
    "ingredients we have",
    "from my pantry",
    "from our pantry",
    "from my grocery",
    "from our grocery",
    "what can i make",
    "what can we make",
    "what can i cook",
    "what can we cook",
    "using what i have",
    "using what we have",
]


def _inventory_recipe_request(message: str) -> bool:
    return _matches_any(message, _INVENTORY_RECIPE_HINTS)


def _normalize_recipe_ingredient(value: str) -> str:
    return " ".join((value or "").strip().split())


def _inventory_recipe_ingredients(db_context: Dict[str, Any]) -> List[str]:
    ingredients: List[str] = []
    seen: set[str] = set()

    def add_item(value: Optional[str]) -> None:
        name = _normalize_recipe_ingredient(str(value or ""))
        if not name:
            return
        lowered = name.lower()
        if lowered in seen:
            return
        seen.add(lowered)
        ingredients.append(name)

    for item in db_context.get("pantry_items", []) or []:
        add_item(item.get("name"))

    for item in db_context.get("pantry_snapshot", []) or []:
        add_item(item.get("name"))

    for item in db_context.get("low_stock_pantry", []) or []:
        add_item(item.get("name"))

    for grocery_list in db_context.get("grocery_lists", []) or []:
        for item in grocery_list.get("items", []) or []:
            if item.get("checked"):
                add_item(item.get("name"))

    return ingredients[:5]


SYSTEM_PROMPT = """You are FamilyOps AI, a warm, practical household operations assistant.
You help families manage tasks, calendars, grocery lists, meal plans, reminders, weather, local events, recipes, and household memory.

Guidelines:
- Be concise, friendly, and helpful — like a knowledgeable family organizer.
- When you have real data from the household, summarize it clearly.
- When asked to create something (task, reminder, event), confirm what was done.
- When asked a general question, answer directly without unnecessary padding.
- Use bullet points for lists of items.
- Never make up data that wasn't provided to you.
"""

INTENT_PROMPT = """Classify this message into exactly one category.
Categories: task, calendar, grocery, meal, recipe, weather, event, reminder, memory, email, shopping, web, general

Message: {message}

Reply with ONLY the category name, nothing else."""


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    agent_name: str
    workflow_id: str
    context: Dict[str, Any]
    tools_called: List[str]
    reply: str
    status: str
    error: Optional[str]


class FamilyOpsOrchestrator:
    def __init__(self):
        self.llm = _build_llm()
        self.llm_provider = "openai" if settings.openai_api_key else "google" if settings.google_api_key else None
        self.llm_model = settings.openai_model if settings.openai_api_key else settings.google_model if settings.google_api_key else None
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("router", self._router_node)
        graph.add_node("task_agent", self._task_agent_node)
        graph.add_node("calendar_agent", self._calendar_agent_node)
        graph.add_node("payment_agent", self._payment_agent_node)
        graph.add_node("grocery_agent", self._grocery_agent_node)
        graph.add_node("meal_agent", self._meal_agent_node)
        graph.add_node("reminder_agent", self._reminder_agent_node)
        graph.add_node("memory_agent", self._memory_agent_node)
        graph.add_node("email_agent", self._email_agent_node)
        graph.add_node("shopping_agent", self._shopping_agent_node)
        graph.add_node("weather_agent", self._weather_agent_node)
        graph.add_node("event_agent", self._event_agent_node)
        graph.add_node("recipe_agent", self._recipe_agent_node)
        graph.add_node("web_search_agent", self._web_search_agent_node)
        graph.add_node("general_agent", self._general_agent_node)

        graph.set_entry_point("router")

        graph.add_conditional_edges(
            "router",
            self._route_to_agent,
            {
                "task": "task_agent",
                "calendar": "calendar_agent",
                "payment": "payment_agent",
                "grocery": "grocery_agent",
                "meal": "meal_agent",
                "reminder": "reminder_agent",
                "memory": "memory_agent",
                "email": "email_agent",
                "shopping": "shopping_agent",
                "weather": "weather_agent",
                "event": "event_agent",
                "recipe": "recipe_agent",
                "web": "web_search_agent",
                "general": "general_agent",
            }
        )

        for node in ["task_agent", "payment_agent","calendar_agent", "grocery_agent", "meal_agent",
                     "reminder_agent", "memory_agent", "email_agent", "shopping_agent", "weather_agent",
                     "event_agent", "recipe_agent", "web_search_agent", "general_agent"]:
            graph.add_edge(node, END)

        return graph.compile()

    async def _router_node(self, state: AgentState) -> AgentState:
        message = state["messages"][-1].content if state["messages"] else ""
        intent = await self._detect_intent(message)
        state["context"]["intent"] = intent
        state["status"] = "routing"
        logger.info("orchestrator.routed", intent=intent, message_preview=message[:80])
        await event_bus.publish("agent.started", {
            "agent": "orchestrator",
            "workflow_id": state["workflow_id"],
            "intent": intent,
        })
        return state

    def _route_to_agent(self, state: AgentState) -> str:
        return state["context"].get("intent", "general")

    def _extract_total_tokens(self, usage: Any) -> int:
        if usage is None:
            return 0

        if hasattr(usage, "model_dump"):
            payload = usage.model_dump()
        elif isinstance(usage, dict):
            payload = dict(usage)
        else:
            return 0

        total_tokens = payload.get("total_tokens")
        if isinstance(total_tokens, (int, float)):
            return int(total_tokens)

        input_tokens = payload.get("input_tokens") or payload.get("prompt_tokens")
        output_tokens = payload.get("output_tokens") or payload.get("completion_tokens")
        if isinstance(input_tokens, (int, float)) or isinstance(output_tokens, (int, float)):
            return int(input_tokens or 0) + int(output_tokens or 0)

        if isinstance(payload.get("input"), (int, float)) or isinstance(payload.get("output"), (int, float)):
            return int(payload.get("input") or 0) + int(payload.get("output") or 0)

        return 0

    def _record_tokens(self, state: AgentState, usage: Any) -> int:
        tokens = self._extract_total_tokens(usage)
        if tokens > 0:
            context = state.setdefault("context", {})
            context["tokens_used"] = int(context.get("tokens_used") or 0) + tokens
        return tokens

    async def _detect_intent(self, message: str) -> str:
        lower = message.lower()

        # Fast-path routes for the new external providers.
        if _matches_any(lower, ["weather", "forecast", "temperature", "rain", "wind", "snow", "sunny", "cloudy", "hail"]):
            return "weather"
        if _matches_any(lower, ["family event", "family events", "events near", "local event", "local events", "things to do", "kids activities", "children activities", "school holiday activities", "school holiday activity", "school holidays", "holiday activities", "days out", "near me"]):
            return "event"
        if _matches_any(lower, ["recipe", "recipes", "how do i make", "how to make", "cook this", "meal idea", "dish idea", "bake"]):
            return "recipe"
        if _matches_any(lower, ["look up", "lookup", "search the web", "web search", "browse the web", "latest", "current", "find online", "online", "internet"]):
            return "web"

        if self.llm:
            trace = start_ai_trace(
                "orchestrator.intent",
                input={"message": message},
                metadata={
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                    **prompt_metadata("orchestrator.intent"),
                },
            )
            try:
                prompt = ChatPromptTemplate.from_template(INTENT_PROMPT)
                chain = prompt | self.llm
                result = await chain.ainvoke({"message": message})
                intent = result.content.strip().lower().split()[0]
                valid = {
                    "task",
                    "calendar",
                    "payment",
                    "grocery",
                    "meal",
                    "recipe",
                    "weather",
                    "event",
                    "reminder",
                    "memory",
                    "email",
                    "shopping",
                    "web",
                    "general",
                }
                end_ai_generation(
                    trace,
                    name="orchestrator.intent",
                    model=self.llm_model or settings.openai_model or settings.google_model,
                    input={"message": message},
                    output=intent,
                    metadata={
                        "provider": self.llm_provider,
                        "model": self.llm_model,
                        **prompt_metadata("orchestrator.intent"),
                    },
                )
                return intent if intent in valid else "general"
            except Exception as e:
                end_ai_generation(
                    trace,
                    name="orchestrator.intent",
                    model=self.llm_model or settings.openai_model or settings.google_model,
                    input={"message": message},
                    output=None,
                    metadata={
                        "provider": self.llm_provider,
                        "model": self.llm_model,
                        **prompt_metadata("orchestrator.intent"),
                    },
                    level="ERROR",
                    status_message=str(e),
                )
                logger.warning("orchestrator.intent_fallback", error=str(e))

        # Keyword fallback
        keywords = {
            "task": ["task", "todo", "chore", "assign", "complete", "finish"],
            "calendar": ["calendar", "schedule", "appointment", "meeting", "invite", "reschedule", "event", "add event"],
            "payment": ["pay", "bill", "invoice", "charge", "payment"], 
            "grocery": ["grocery", "list", "food"],
            "shopping": ["shop", "shopping", "buy", "product", "price", "recommend", "store", "deal"],
            "web": ["web", "look up", "lookup", "latest", "current", "news", "online", "internet", "find online"],
            "meal": ["meal", "dinner", "lunch", "breakfast", "cook", "eat", "meal plan", "weekly meals"],
            "reminder": ["remind", "reminder", "alert", "notify", "alarm"],
            "memory": ["remember", "memory", "store", "note", "know"],
            "email": ["email", "mail", "inbox", "message"],
        }
        for intent, kws in keywords.items():
            if any(kw in lower for kw in kws):
                return intent
        return "general"

    async def _call_llm(self, user_message: str, context_text: str, agent_label: str, state: AgentState) -> str:
        if not self.llm:
            return (
                f"⚠️ No AI key configured. Add **OPENAI_API_KEY** to `backend/.env` to enable real responses.\n\n"
                f"Your message was routed to the **{agent_label}** agent."
            )
        safe_context_text = redact_pii(context_text, source=f"orchestrator.{agent_label.lower()}", field="context")
        trace = start_ai_trace(
            f"orchestrator.{agent_label.lower()}",
            input={
                "context": safe_context_text,
                "message": user_message,
            },
            metadata={
                "provider": self.llm_provider,
                "model": self.llm_model,
                "agent": agent_label,
                **prompt_metadata("orchestrator.system"),
            },
        )
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"{safe_context_text}\n\nUser: {user_message}" if safe_context_text else user_message),
        ]
        try:
            response = await self.llm.ainvoke(messages)
            usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None)
            self._record_tokens(state, usage)
            end_ai_generation(
                trace,
                name=f"orchestrator.{agent_label.lower()}",
                model=self.llm_model or settings.openai_model or settings.google_model,
                input=[message.content for message in messages],
                output=response.content,
                usage=usage,
                metadata={
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                    "agent": agent_label,
                    **prompt_metadata("orchestrator.system"),
                },
            )
            return response.content
        except Exception as e:
            if self.llm_provider == "openai" and settings.google_api_key:
                try:
                    fallback_llm = _build_google_or_openai_fallback("google", settings.google_model)
                    if fallback_llm:
                        response = await fallback_llm.ainvoke(messages)
                        self.llm = fallback_llm
                        self.llm_provider = "google"
                        self.llm_model = settings.google_model
                        usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None)
                        self._record_tokens(state, usage)
                        end_ai_generation(
                            trace,
                            name=f"orchestrator.{agent_label.lower()}",
                            model=self.llm_model,
                            input=[message.content for message in messages],
                            output=response.content,
                            usage=usage,
                            metadata={
                                "provider": self.llm_provider,
                                "model": self.llm_model,
                                "agent": agent_label,
                                "fallback": True,
                                **prompt_metadata("orchestrator.system"),
                            },
                        )
                        logger.warning(
                            "orchestrator.google_fallback",
                            requested_model=settings.openai_model,
                            fallback_model=settings.google_model,
                            error=str(e),
                        )
                        return response.content
                except Exception as fallback_error:
                    logger.warning(
                        "orchestrator.google_fallback_failed",
                        requested_model=settings.openai_model,
                        fallback_model=settings.google_model,
                        error=str(fallback_error),
                    )

            if self.llm_provider == "openai" and is_openai_model_not_found_error(e):
                for model_name in openai_chat_model_candidates():
                    if model_name == self.llm_model:
                        continue
                    try:
                        fallback_llm = _build_openai_llm(model_name)
                        response = await fallback_llm.ainvoke(messages)
                        self.llm = fallback_llm
                        self.llm_provider = "openai"
                        self.llm_model = model_name
                        usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None)
                        self._record_tokens(state, usage)
                        end_ai_generation(
                            trace,
                            name=f"orchestrator.{agent_label.lower()}",
                            model=self.llm_model,
                            input=[message.content for message in messages],
                            output=response.content,
                            usage=usage,
                            metadata={
                                "provider": self.llm_provider,
                                "model": self.llm_model,
                                "agent": agent_label,
                                "fallback": True,
                                **prompt_metadata("orchestrator.system"),
                            },
                        )
                        logger.warning(
                            "orchestrator.openai_model_fallback",
                            requested_model=settings.openai_model,
                            fallback_model=model_name,
                        )
                        return response.content
                    except Exception as fallback_error:
                        logger.warning(
                            "orchestrator.openai_model_fallback_failed",
                            requested_model=settings.openai_model,
                            fallback_model=model_name,
                            error=str(fallback_error),
                        )

            if self.llm_provider == "google" and _is_missing_google_model_error(e):
                for model_name in _google_model_fallbacks(settings.google_model):
                    if model_name == self.llm_model:
                        continue
                    try:
                        fallback_llm = _build_google_or_openai_fallback("google", model_name)
                        if not fallback_llm:
                            continue
                        response = await fallback_llm.ainvoke(messages)
                        self.llm = fallback_llm
                        self.llm_model = model_name
                        usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None)
                        self._record_tokens(state, usage)
                        end_ai_generation(
                            trace,
                            name=f"orchestrator.{agent_label.lower()}",
                            model=self.llm_model,
                            input=[message.content for message in messages],
                            output=response.content,
                            usage=usage,
                            metadata={
                                "provider": self.llm_provider,
                                "model": self.llm_model,
                                "agent": agent_label,
                                "fallback": True,
                            },
                        )
                        logger.warning(
                            "orchestrator.google_model_fallback",
                            requested_model=settings.google_model,
                            fallback_model=model_name,
                        )
                        return response.content
                    except Exception as fallback_error:
                        logger.warning(
                            "orchestrator.google_model_fallback_failed",
                            requested_model=settings.google_model,
                            fallback_model=model_name,
                            error=str(fallback_error),
                        )

                if settings.openai_api_key:
                    try:
                        fallback_llm = _build_google_or_openai_fallback("openai")
                        if fallback_llm:
                            response = await fallback_llm.ainvoke(messages)
                            self.llm = fallback_llm
                            self.llm_provider = "openai"
                            self.llm_model = settings.openai_model
                            usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", None)
                            self._record_tokens(state, usage)
                            end_ai_generation(
                                trace,
                                name=f"orchestrator.{agent_label.lower()}",
                                model=self.llm_model,
                                input=[message.content for message in messages],
                                output=response.content,
                                usage=usage,
                                metadata={
                                    "provider": self.llm_provider,
                                    "model": self.llm_model,
                                    "agent": agent_label,
                                    "fallback": True,
                                    **prompt_metadata("orchestrator.system"),
                                },
                            )
                            logger.warning(
                                "orchestrator.openai_fallback",
                                requested_model=settings.google_model,
                                fallback_model=settings.openai_model,
                            )
                            return response.content
                    except Exception as fallback_error:
                        logger.warning(
                            "orchestrator.openai_fallback_failed",
                            requested_model=settings.google_model,
                            fallback_model=settings.openai_model,
                            error=str(fallback_error),
                        )

            logger.error("orchestrator.llm_error", error=str(e))
            end_ai_generation(
                trace,
                name=f"orchestrator.{agent_label.lower()}",
                model=self.llm_model or settings.openai_model or settings.google_model,
                input=[message.content for message in messages],
                output=None,
                metadata={
                    "provider": self.llm_provider,
                    "model": self.llm_model,
                    "agent": agent_label,
                    **prompt_metadata("orchestrator.system"),
                },
                level="ERROR",
                status_message=str(e),
            )
            return f"Sorry, I ran into an error: {str(e)}"

    # ─── Task Agent ────────────────────────────────────────────────────────────

    async def _task_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("task_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

        tasks = db_context.get("tasks", [])
        context_text = ""
        if tasks:
            pending = [t for t in tasks if t.get("status") == "pending"]
            overdue = [t for t in tasks if t.get("overdue")]
            context_text = f"Current household tasks ({len(tasks)} total, {len(pending)} pending, {len(overdue)} overdue):\n"
            for t in tasks[:10]:
                context_text += f"- [{t['status']}] {t['title']} (priority: {t['priority']})"
                if t.get("due_date"):
                    context_text += f", due: {t['due_date']}"
                context_text += "\n"

        reply = await self._call_llm(message, context_text, "Task", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Calendar Agent ─────────────────────────────────────────────────────────

    async def _calendar_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("calendar_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

        events = db_context.get("events", [])
        context_text = ""
        if events:
            context_text = f"Upcoming calendar events ({len(events)}):\n"
            for e in events[:10]:
                context_text += f"- {e['title']} on {e['start_time']}"
                if e.get("location"):
                    context_text += f" at {e['location']}"
                context_text += "\n"

        reply = await self._call_llm(message, context_text, "Calendar", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Grocery Agent ──────────────────────────────────────────────────────────

    async def _grocery_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("grocery_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})
        db = state["context"].get("db")

        if _is_create_request(message, ["grocery", "shopping list", "groceries", "shop"]):
            if db is None:
                state["reply"] = "I can create the grocery list, but the database session was not available."
            else:
                created = await create_grocery_list_from_message(db, message, db_context)
                state["reply"] = created["reply"]
                state["context"]["resource"] = created["resource"]
            state["status"] = "completed"
            await self._finish(state)
            return state

        lists = db_context.get("grocery_lists", [])
        context_text = ""
        if lists:
            context_text = f"Current grocery lists ({len(lists)}):\n"
            for gl in lists[:5]:
                items = gl.get("items", [])
                unchecked = [i for i in items if not i.get("checked")]
                context_text += f"- **{gl['name']}**: {len(unchecked)} items remaining"
                if unchecked:
                    context_text += f" ({', '.join(i['name'] for i in unchecked[:5])})"
                context_text += "\n"

        reply = await self._call_llm(message, context_text, "Grocery", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Meal Agent ─────────────────────────────────────────────────────────────

    async def _meal_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("meal_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})
        db = state["context"].get("db")

        if _is_create_request(message, ["meal", "meals", "meal plan", "plan"]):
            if db is None:
                state["reply"] = "I can create the meal plan, but the database session was not available."
            else:
                created = await create_meal_plan_from_message(db, message, db_context)
                state["reply"] = created["reply"]
                state["context"]["resource"] = created["resource"]
            state["status"] = "completed"
            await self._finish(state)
            return state

        plans = db_context.get("meal_plans", [])
        members = db_context.get("family_members", [])
        context_text = ""
        if members:
            restrictions = []
            for m in members:
                if m.get("dietary_restrictions"):
                    restrictions.append(f"{m['name']}: {', '.join(m['dietary_restrictions'])}")
            if restrictions:
                context_text += f"Dietary restrictions:\n" + "\n".join(f"- {r}" for r in restrictions) + "\n\n"
        if plans:
            latest = plans[0]
            context_text += f"Latest meal plan (week of {latest.get('week_start', 'N/A')[:10]}):\n"
            for day, meals in (latest.get("meals") or {}).items():
                if isinstance(meals, dict):
                    context_text += f"- {day.capitalize()}: {meals.get('breakfast', '?')} / {meals.get('lunch', '?')} / {meals.get('dinner', '?')}\n"

        reply = await self._call_llm(message, context_text, "Meal", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Reminder Agent ─────────────────────────────────────────────────────────

    async def _reminder_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("reminder_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

        reminders = db_context.get("reminders", [])
        context_text = ""
        if reminders:
            pending = [r for r in reminders if r.get("status") == "pending"]
            context_text = f"Upcoming reminders ({len(pending)} pending):\n"
            for r in pending[:8]:
                context_text += f"- {r['title']} at {r.get('remind_at', 'N/A')}"
                if r.get("recurrence"):
                    context_text += f" ({r['recurrence']})"
                context_text += "\n"

        reply = await self._call_llm(message, context_text, "Reminder", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Memory Agent ───────────────────────────────────────────────────────────

    async def _memory_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("memory_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

        memories = db_context.get("memories", [])
        context_text = ""
        if memories:
            context_text = f"Relevant household memories ({len(memories)}):\n"
            for m in memories[:8]:
                memory_type = m.get("memory_type") or m.get("category") or "general"
                context_text += f"- [{memory_type}] {m['content']}\n"

        reply = await self._call_llm(message, context_text, "Memory", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # Add payment agent
    async def _payment_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("payment_agent")
        message = state["messages"][-1].content
        
        # Extract bill details from email context
        bill_context = state["context"].get("bill_context", {})
        context_text = f"Bill: {bill_context.get('description')} | Amount:                             {bill_context.get('amount')} | Due: {bill_context.get('due_date')}"
        
        reply = await self._call_llm(message, context_text, "Payment", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state
    
    # ─── Email Agent ────────────────────────────────────────────────────────────

    async def _email_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("email_agent")
        message = state["messages"][-1].content
        context_text = "Email ingestion is available. Configure IMAP credentials in Settings to enable automatic email processing and action-item extraction."
        reply = await self._call_llm(message, context_text, "Email", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Shopping Agent ─────────────────────────────────────────────────────────

    async def _shopping_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("shopping_agent")
        message = state["messages"][-1].content
        context_text = "Shopping assistance available: search products, compare prices, get recommendations, find alternatives, track prices, and view favorites."
        reply = await self._call_llm(message, context_text, "Shopping", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Weather Agent ─────────────────────────────────────────────────────────

    async def _weather_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("weather_agent")
        message = state["messages"][-1].content
        location = _extract_location_from_message(message) or message

        try:
            weather = await weather_service.search(location, forecast_days=5)
        except Exception as e:
            logger.warning("weather.search_failed", error=str(e))
            state["reply"] = f"I couldn’t fetch the weather right now: {str(e)}"
            state["status"] = "completed"
            await self._finish(state)
            return state

        context_lines = [f"Weather for {weather.get('location', {}).get('name', location)}"]
        current = weather.get("current") or {}
        if current:
            context_lines.append(
                f"Current: {current.get('temperature')}°C, {current.get('summary')}, wind {current.get('wind_speed')} km/h"
            )
        for day in (weather.get("daily") or [])[:5]:
            context_lines.append(
                f"{day.get('date')}: {day.get('summary')} | {day.get('temperature_min')}°C to {day.get('temperature_max')}°C"
            )

        context_text = "\n".join(context_lines)
        reply = _format_weather_reply(location, weather)
        state["reply"] = reply
        state["context"]["resource"] = {
            "type": "weather_search",
            "query": message,
            "location": weather.get("location", {}),
            "current": current,
            "daily": weather.get("daily") or [],
        }
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Event Agent ───────────────────────────────────────────────────────────

    async def _event_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("event_agent")
        message = state["messages"][-1].content
        location = _extract_location_from_message(message)

        try:
            activities = await activity_search_service.search(
                message,
                location=location,
                source_domains=_activity_source_domains(message),
                max_results=8,
            )
        except Exception as e:
            logger.warning("events.search_failed", error=str(e))
            state["reply"] = f"I couldn’t search local activities right now: {str(e)}"
            state["status"] = "completed"
            await self._finish(state)
            return state

        results = activities.get("results") or []
        pages = activities.get("pages") or []
        context_text = _format_activity_reply(location, results, pages)
        reply = context_text
        state["reply"] = reply
        state["context"]["resource"] = {
            "type": "activity_search",
            "query": message,
            "location": location,
            "results": results,
            "pages": pages,
            "sources": activities.get("sources") or {},
            "search_query": activities.get("query", message),
        }
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Recipe Agent ──────────────────────────────────────────────────────────

    async def _recipe_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("recipe_agent")
        message = state["messages"][-1].content
        query = _extract_recipe_query(message)
        db_context = state["context"].get("db_context", {})
        ingredient_hints = _inventory_recipe_ingredients(db_context) if _inventory_recipe_request(message) else []

        try:
            recipes = await recipe_search_service.search(
                query,
                max_results=8,
                ingredients=ingredient_hints,
            )
        except Exception as e:
            logger.warning("recipes.search_failed", error=str(e))
            state["reply"] = f"I couldn’t search recipes right now: {str(e)}"
            state["status"] = "completed"
            await self._finish(state)
            return state

        results = recipes.get("results") or []
        context_label = query
        if ingredient_hints:
            context_label = f"{query} using {', '.join(ingredient_hints)}"

        context_lines = [f"Recipe search results for: {context_label}"]
        if ingredient_hints:
            context_lines.append(f"Available ingredients used: {', '.join(ingredient_hints)}")
        for idx, item in enumerate(results[:8], start=1):
            ingredients = ", ".join((item.get("ingredients") or [])[:6])
            context_lines.append(
                f"{idx}. {item.get('name')} ({item.get('category')}, {item.get('area')})"
                f"\n   Ingredients: {ingredients}"
            )

        context_text = "\n".join(context_lines) if results else "No recipes were found."
        reply = await self._call_llm(message, context_text, "Recipe", state) if self.llm else context_text
        state["reply"] = reply
        state["context"]["resource"] = {
            "type": "recipe_search",
            "query": query,
            "ingredients": ingredient_hints,
            "results": results,
        }
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Web Search Agent ─────────────────────────────────────────────────────

    async def _web_search_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("web_search_agent")
        message = state["messages"][-1].content

        try:
            search_results = await web_search_service.search(
                message,
                max_results=5,
                fetch_pages=True,
            )
        except Exception as e:
            logger.warning("web_search.failed", error=str(e))
            state["reply"] = f"I couldn’t search the web right now: {str(e)}"
            state["status"] = "completed"
            await self._finish(state)
            return state

        reply = _format_web_search_reply(message, search_results)

        state["reply"] = reply
        state["context"]["resource"] = {
            "type": "web_search",
            "query": search_results.get("query", message),
            "provider": search_results.get("provider", "duckduckgo"),
            "results": search_results.get("pages") or search_results.get("results") or [],
        }
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── General Agent ──────────────────────────────────────────────────────────

    async def _general_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("general_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

        parts = []
        if db_context.get("tasks"):
            pending = sum(1 for t in db_context["tasks"] if t.get("status") == "pending")
            parts.append(f"{pending} pending tasks")
        if db_context.get("events"):
            parts.append(f"{len(db_context['events'])} upcoming events")
        if db_context.get("reminders"):
            pending_r = sum(1 for r in db_context["reminders"] if r.get("status") == "pending")
            parts.append(f"{pending_r} pending reminders")
        if db_context.get("family_members"):
            parts.append(f"{len(db_context['family_members'])} family members")

        context_text = f"Household snapshot: {', '.join(parts)}." if parts else ""
        reply = await self._call_llm(message, context_text, "General", state)
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    async def _finish(self, state: AgentState):
        await event_bus.publish("agent.completed", {
            "workflow_id": state["workflow_id"],
            "tools_called": state["tools_called"],
        })

    # ─── Public run method ───────────────────────────────────────────────────────

    async def run(self, message: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        import uuid
        workflow_id = str(uuid.uuid4())

        initial_state = AgentState(
            messages=[HumanMessage(content=message)],
            agent_name="orchestrator",
            workflow_id=workflow_id,
            context=context or {},
            tools_called=[],
            reply="",
            status="started",
            error=None,
        )

        try:
            result = await self.graph.ainvoke(initial_state)
            public_context = {
                key: value
                for key, value in (result.get("context") or {}).items()
                if key != "db"
            }
            return {
                "workflow_id": workflow_id,
                "status": result["status"],
                "reply": result.get("reply", ""),
                "context": public_context,
                "tools_called": result["tools_called"],
                "tokens_used": int(public_context.get("tokens_used") or 0),
            }
        except Exception as e:
            logger.error("orchestrator.run_error", error=str(e))
            return {
                "workflow_id": workflow_id,
                "status": "failed",
                "reply": f"Sorry, something went wrong: {str(e)}",
                "error": str(e),
                "context": {},
                "tools_called": [],
            }


orchestrator = FamilyOpsOrchestrator()
