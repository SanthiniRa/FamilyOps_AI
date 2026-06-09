from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional
from app.tools.mcp_tools import MCPTools
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from app.core.config import settings
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.services.openai_utils import (
    is_openai_model_not_found_error,
    openai_chat_model_candidates,
)
import json
import re
from datetime import datetime, timezone
from sqlalchemy import select


tools = MCPTools()


# ============================================================
# STATE
# ============================================================
class EmailState(TypedDict):
    email: Dict[str, Any]
    actions: List[Dict[str, Any]]
    calendar_events: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]
    memory: List[Dict[str, Any]]
    routing: List[tuple[str, Dict[str, Any]]]
    processed: bool
    category: str


_SCHOOL_ACTION_HINTS = (
    "permission slip",
    "permission",
    "form",
    "deadline",
    "due",
    "return",
    "sign",
    "signed",
    "submit",
    "rsvp",
    "register",
    "registration",
    "volunteer",
    "conference",
    "pickup",
    "drop off",
    "field trip",
    "fees",
    "payment",
    "buy",
    "bring",
    "send in",
    "review",
    "complete",
    "respond",
    "reply",
)

_SCHOOL_EMAIL_HINTS = (
    "school",
    "teacher",
    "class",
    "classroom",
    "principal",
    "pta",
    "pto",
    "student",
    "district",
    "homeroom",
    "counselor",
    "bus route",
    "after school",
    "elementary",
    "middle school",
    "high school",
)


def _clean_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _looks_like_school_email(email: Dict[str, Any]) -> bool:
    text = " ".join(
        _clean_text(email.get(part))
        for part in ("subject", "body_text", "body_html", "attachment_text", "sender")
    ).lower()
    return any(hint in text for hint in _SCHOOL_EMAIL_HINTS)


def _extract_fallback_tasks(email: Dict[str, Any]) -> List[Dict[str, str]]:
    subject = _clean_text(email.get("subject"))
    body = _clean_text(email.get("body_text"))
    attachment_text = _clean_text(email.get("attachment_text"))
    sender = _clean_text(email.get("sender"))
    combined = f"{subject}. {body}. {attachment_text}".strip()
    lower = combined.lower()

    if not combined:
        return []

    if not _looks_like_school_email(email):
        return []

    if not any(hint in lower for hint in _SCHOOL_ACTION_HINTS):
        return []

    text_source = attachment_text or body or subject
    sentences = re.split(r"(?<=[.!?])\s+|\n+", text_source)
    tasks: List[Dict[str, str]] = []
    seen = set()

    for sentence in sentences:
        cleaned = _clean_text(sentence)
        if not cleaned:
            continue

        lowered = cleaned.lower()
        if not any(hint in lowered for hint in _SCHOOL_ACTION_HINTS):
            continue

        title = cleaned
        title = re.sub(r"^(please|kindly|students should|parents should|action required:)\s+", "", title, flags=re.I)
        title = title[:120].rstrip(" ,;:-")
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        tasks.append({
            "type": "task",
            "title": title,
            "description": f"School email from {sender or 'unknown sender'}: {cleaned}",
        })

        if len(tasks) >= 3:
            break

    if tasks:
        return tasks

    # When the email looks actionable but we could not isolate a sentence,
    # fall back to a single task so the family does not miss the message.
    return [{
        "type": "task",
        "title": subject[:120] if subject else "Review school email",
        "description": f"Review email from {sender or 'school'} for any required action.",
    }]


async def _persist_email_result(email_id: Optional[str], tasks: List[Dict[str, Any]], calendar_events: List[Dict[str, Any]], memory: List[Dict[str, Any]]):
    if not email_id:
        return

    from app.db.database import AsyncSessionLocal
    from app.db.models import Email

    category = "task" if tasks else "calendar" if calendar_events else "memory" if memory else "inbox"
    action_items = tasks or calendar_events or memory or []
    summary_bits = []
    if tasks:
        summary_bits.append(f"{len(tasks)} task(s)")
    if calendar_events:
        summary_bits.append(f"{len(calendar_events)} event(s)")
    if memory:
        summary_bits.append(f"{len(memory)} memory item(s)")
    summary = ", ".join(summary_bits) if summary_bits else "No actionable items found"

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Email).where(Email.id == email_id))
        email = result.scalar_one_or_none()
        if not email:
            return
        email.processed = True
        email.category = category
        email.action_items = action_items
        email.summary = summary
        email.extra_data = {
            **(email.extra_data or {}),
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        db.add(email)
        await db.commit()


# ============================================================
# LLM NODE: EXTRACT STRUCTURE
# ============================================================
async def extract_node(state: EmailState):
    email = state["email"]
    attachment_count = len(email.get("attachments", []) or [])
    attachment_text = _clean_text(email.get("attachment_text"))
    body_html = _clean_text(email.get("body_html"))

    prompt = f"""
Extract structured data from this email.

Return JSON:
{{
  "tasks": [],
  "calendar_events": [],
  "memory": []
}}

Email:
Subject: {email.get("subject", "")}
Sender: {email.get("sender", "")}
{email["body_text"]}

Attachment count: {attachment_count}

Attachment text:
{attachment_text or "None"}

HTML body:
{body_html or "None"}

Rules:
- Return task items for concrete actions the family must do.
- School emails often include permission slips, forms, deadlines, pickup changes, conference RSVPs, or supply requests.
- If the email is actionable but the model is unsure, prefer a task rather than leaving it empty.
"""

    response = None
    last_error = None
    trace = start_ai_trace(
        "email.extract",
        input=prompt,
        metadata={
            "subject": email.get("subject", ""),
            "sender": email.get("sender", ""),
        },
    )
    for model_name in openai_chat_model_candidates():
        model = ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        try:
            response = await model.ainvoke([HumanMessage(content=prompt)])
            end_ai_generation(
                trace,
                name="email.extract",
                model=model_name,
                input=prompt,
                output=response.content,
                metadata={
                    "subject": email.get("subject", ""),
                    "sender": email.get("sender", ""),
                },
            )
            break
        except Exception as e:
            last_error = e
            if not is_openai_model_not_found_error(e):
                end_ai_generation(
                    trace,
                    name="email.extract",
                    model=model_name,
                    input=prompt,
                    output=None,
                    metadata={
                        "subject": email.get("subject", ""),
                        "sender": email.get("sender", ""),
                    },
                    level="ERROR",
                    status_message=str(e),
                )
                raise

    if response is None:
        end_ai_generation(
            trace,
            name="email.extract",
            model=openai_chat_model_candidates()[0] if openai_chat_model_candidates() else settings.openai_model,
            input=prompt,
            output=None,
            metadata={
                "subject": email.get("subject", ""),
                "sender": email.get("sender", ""),
            },
            level="ERROR",
            status_message=str(last_error) if last_error else "Unknown error",
        )
        raise last_error  # type: ignore[misc]

    raw = response.content.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    start = raw.find("{")
    end = raw.rfind("}") + 1
    raw = raw[start:end] if start >= 0 and end > start else raw

    try:
        data = json.loads(raw)
    except Exception:
        data = {"tasks": [], "calendar_events": [], "memory": []}

    tasks = data.get("tasks", []) or []
    calendar_events = data.get("calendar_events", []) or []
    memory = data.get("memory", []) or []

    if not tasks:
        tasks = _extract_fallback_tasks(email)

    return {
        **state,
        "tasks": tasks,
        "calendar_events": calendar_events,
        "memory": memory,
        "processed": False,
        "category": "task" if tasks else "calendar" if calendar_events else "memory" if memory else "inbox",
    }


# ============================================================
# ROUTER NODE
# ============================================================
async def router_node(state: EmailState):
    outputs = []

    for task in state["tasks"]:
        outputs.append(("task", task))

    for event in state["calendar_events"]:
        outputs.append(("calendar", event))

    for mem in state["memory"]:
        outputs.append(("memory", mem))

    return {"routing": outputs}


# ============================================================
# EXECUTOR NODE (MCP CALLS)
# ============================================================
async def executor_node(state: EmailState):
    routing = state.get("routing", [])

    for action_type, payload in routing:

        if action_type == "task":
            await tools.create_task(payload)

        elif action_type == "calendar":
            await tools.create_event(payload)

        elif action_type == "memory":
            await tools.store_memory(payload)

    await _persist_email_result(
        state.get("email", {}).get("id"),
        state.get("tasks", []),
        state.get("calendar_events", []),
        state.get("memory", []),
    )

    # Mark the graph step as having made progress so LangGraph accepts the update.
    return {
        "processed": True,
        "category": state.get("category", "inbox"),
    }


# ============================================================
# GRAPH BUILD
# ============================================================
def build_graph():
    graph = StateGraph(EmailState)

    graph.add_node("extract", extract_node)
    graph.add_node("router", router_node)
    graph.add_node("execute", executor_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "router")
    graph.add_edge("router", "execute")
    graph.add_edge("execute", END)

    return graph.compile()
