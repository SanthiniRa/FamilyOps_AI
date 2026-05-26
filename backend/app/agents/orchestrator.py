from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from app.core.config import settings
from app.core.logging import logger
from app.events.bus import event_bus
import operator
from datetime import datetime


def _build_llm():
    if settings.google_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.google_api_key,
            temperature=0.3,
        )
    elif settings.openai_api_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.3,
        )
    return None


SYSTEM_PROMPT = """You are FamilyOps AI, a warm, practical household operations assistant.
You help families manage tasks, calendars, grocery lists, meal plans, reminders, and household memory.

Guidelines:
- Be concise, friendly, and helpful — like a knowledgeable family organizer.
- When you have real data from the household, summarize it clearly.
- When asked to create something (task, reminder, event), confirm what was done.
- When asked a general question, answer directly without unnecessary padding.
- Use bullet points for lists of items.
- Never make up data that wasn't provided to you.
"""

INTENT_PROMPT = """Classify this message into exactly one category.
Categories: task, calendar, grocery, meal, reminder, memory, email, general

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
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("router", self._router_node)
        graph.add_node("task_agent", self._task_agent_node)
        graph.add_node("calendar_agent", self._calendar_agent_node)
        graph.add_node("grocery_agent", self._grocery_agent_node)
        graph.add_node("meal_agent", self._meal_agent_node)
        graph.add_node("reminder_agent", self._reminder_agent_node)
        graph.add_node("memory_agent", self._memory_agent_node)
        graph.add_node("email_agent", self._email_agent_node)
        graph.add_node("general_agent", self._general_agent_node)

        graph.set_entry_point("router")

        graph.add_conditional_edges(
            "router",
            self._route_to_agent,
            {
                "task": "task_agent",
                "calendar": "calendar_agent",
                "grocery": "grocery_agent",
                "meal": "meal_agent",
                "reminder": "reminder_agent",
                "memory": "memory_agent",
                "email": "email_agent",
                "general": "general_agent",
            }
        )

        for node in ["task_agent", "calendar_agent", "grocery_agent", "meal_agent",
                     "reminder_agent", "memory_agent", "email_agent", "general_agent"]:
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

    async def _detect_intent(self, message: str) -> str:
        if self.llm:
            try:
                prompt = ChatPromptTemplate.from_template(INTENT_PROMPT)
                chain = prompt | self.llm
                result = await chain.ainvoke({"message": message})
                intent = result.content.strip().lower().split()[0]
                valid = {"task", "calendar", "grocery", "meal", "reminder", "memory", "email", "general"}
                return intent if intent in valid else "general"
            except Exception as e:
                logger.warning("orchestrator.intent_fallback", error=str(e))

        # Keyword fallback
        lower = message.lower()
        keywords = {
            "task": ["task", "todo", "chore", "assign", "complete", "finish"],
            "calendar": ["calendar", "event", "schedule", "appointment", "meeting"],
            "grocery": ["grocery", "shopping", "buy", "store", "list", "food"],
            "meal": ["meal", "recipe", "dinner", "lunch", "breakfast", "cook", "eat"],
            "reminder": ["remind", "reminder", "alert", "notify", "alarm"],
            "memory": ["remember", "memory", "store", "note", "know"],
            "email": ["email", "mail", "inbox", "message"],
        }
        for intent, kws in keywords.items():
            if any(kw in lower for kw in kws):
                return intent
        return "general"

    async def _call_llm(self, user_message: str, context_text: str, agent_label: str) -> str:
        if not self.llm:
            return (
                f"⚠️ No AI key configured. Add **GOOGLE_API_KEY** to `backend/.env` to enable real responses.\n\n"
                f"Your message was routed to the **{agent_label}** agent."
            )
        try:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"{context_text}\n\nUser: {user_message}" if context_text else user_message),
            ]
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error("orchestrator.llm_error", error=str(e))
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

        reply = await self._call_llm(message, context_text, "Task")
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

        reply = await self._call_llm(message, context_text, "Calendar")
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Grocery Agent ──────────────────────────────────────────────────────────

    async def _grocery_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("grocery_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

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

        reply = await self._call_llm(message, context_text, "Grocery")
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Meal Agent ─────────────────────────────────────────────────────────────

    async def _meal_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("meal_agent")
        message = state["messages"][-1].content
        db_context = state["context"].get("db_context", {})

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

        reply = await self._call_llm(message, context_text, "Meal")
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

        reply = await self._call_llm(message, context_text, "Reminder")
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
                context_text += f"- [{m.get('category', 'general')}] {m['content']}\n"

        reply = await self._call_llm(message, context_text, "Memory")
        state["reply"] = reply
        state["status"] = "completed"
        await self._finish(state)
        return state

    # ─── Email Agent ────────────────────────────────────────────────────────────

    async def _email_agent_node(self, state: AgentState) -> AgentState:
        state["tools_called"].append("email_agent")
        message = state["messages"][-1].content
        context_text = "Email ingestion is available. Configure IMAP credentials in Settings to enable automatic email processing and action-item extraction."
        reply = await self._call_llm(message, context_text, "Email")
        state["reply"] = reply
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
        reply = await self._call_llm(message, context_text, "General")
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
            return {
                "workflow_id": workflow_id,
                "status": result["status"],
                "reply": result.get("reply", ""),
                "context": result["context"],
                "tools_called": result["tools_called"],
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
