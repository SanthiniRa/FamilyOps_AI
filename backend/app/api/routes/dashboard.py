from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.prompt_versioning import PROMPT_REGISTRY_VERSION, prompt_versions
from app.db.database import get_db
from app.db.models import Task, CalendarEvent, GroceryList, MealPlan, Reminder, AgentRun, HouseholdMemory, FamilyMember, Email
from app.services.email_filter import evaluate_email_importance, important_email_keywords
from app.observability.token_tracker import (
    token_tracker
)
from app.core.resilience import shared_resilience_health
from typing import Any, Dict, List

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _normalize_json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, type(fallback)):
        return value
    return fallback

def _matched_email_keywords(email: Email) -> List[str]:
    extra_data = email.extra_data or {}
    stored_keywords = extra_data.get("matched_keywords") if isinstance(extra_data, dict) else None
    if isinstance(stored_keywords, list) and stored_keywords:
        return [str(keyword).strip().lower() for keyword in stored_keywords if str(keyword).strip()]

    importance = _email_importance(email)
    return importance.matched_keywords


def _email_importance(email: Email):
    extra_data = email.extra_data or {}
    attachment_text = extra_data.get("attachment_text", "") if isinstance(extra_data, dict) else ""
    return evaluate_email_importance(
        subject=getattr(email, "subject", "") or "",
        sender=getattr(email, "sender", "") or "",
        body_text=getattr(email, "body_text", "") or "",
        body_html=getattr(email, "body_html", "") or "",
        attachment_text=attachment_text,
        summary=getattr(email, "summary", "") or "",
        action_items=getattr(email, "action_items", []) or [],
        category=getattr(email, "category", None),
    )


def _important_email_reason(email: Email, matched_keywords: List[str]) -> str:
    extra_data = email.extra_data or {}
    reason = extra_data.get("importance_reason") if isinstance(extra_data, dict) else None
    if reason:
        return str(reason)

    importance = _email_importance(email)
    return importance.reason


def _serialize_important_email(email: Email, matched_keywords: List[str]) -> Dict[str, Any]:
    snippet_source = email.summary or email.body_text or ""
    snippet = " ".join(snippet_source.split())
    if len(snippet) > 180:
        snippet = f"{snippet[:177].rstrip()}..."

    extra_data = email.extra_data or {}
    importance = _email_importance(email)
    subject_keywords = extra_data.get("subject_keywords") if isinstance(extra_data, dict) else None
    matched_senders = extra_data.get("matched_senders") if isinstance(extra_data, dict) else []
    matched_domains = extra_data.get("matched_domains") if isinstance(extra_data, dict) else []

    return {
        "id": email.id,
        "subject": email.subject,
        "sender": email.sender,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "category": email.category,
        "summary": email.summary,
        "action_item_count": len(email.action_items or []),
        "matched_keywords": matched_keywords or importance.matched_keywords,
        "subject_keywords": subject_keywords or importance.subject_keywords,
        "matched_senders": matched_senders or importance.matched_senders,
        "matched_domains": matched_domains or importance.matched_domains,
        "reason": _important_email_reason(email, matched_keywords),
        "snippet": snippet,
    }


def _select_important_emails(emails: List[Email]) -> List[Dict[str, Any]]:
    scored = []
    for email in emails:
        importance = _email_importance(email)
        matched_keywords = importance.matched_keywords
        actionable = importance.is_important

        if not actionable:
            continue

        received_at = email.received_at or datetime.min.replace(tzinfo=timezone.utc)
        scored.append((importance.score, received_at, email, matched_keywords))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        _serialize_important_email(email, matched_keywords)
        for _, _, email, matched_keywords in scored[:5]
    ]


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    week_end = now + timedelta(days=7)

    tasks_result = await db.execute(select(Task))
    tasks = tasks_result.scalars().all()

    events_result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.start_time >= now,
            CalendarEvent.start_time <= week_end
        )
    )
    upcoming_events = events_result.scalars().all()

    reminders_result = await db.execute(
        select(Reminder).where(
            Reminder.remind_at >= today_start,
            Reminder.remind_at < today_end,
            Reminder.status == "pending"
        )
    )
    today_reminders = reminders_result.scalars().all()

    grocery_result = await db.execute(
        select(GroceryList).where(GroceryList.status == "active")
    )
    active_lists = grocery_result.scalars().all()

    agent_result = await db.execute(
        select(AgentRun).order_by(AgentRun.started_at.desc()).limit(5)
    )
    recent_runs = agent_result.scalars().all()

    members_result = await db.execute(select(FamilyMember))
    members = members_result.scalars().all()

    emails_result = await db.execute(
        select(Email)
        .where(
            Email.received_at >= today_start,
            Email.received_at < today_end,
        )
        .order_by(Email.received_at.desc())
        .limit(50)
    )
    today_emails = emails_result.scalars().all()
    important_emails = _select_important_emails(today_emails)

    pending_tasks = [t for t in tasks if t.status == "pending"]
    overdue_tasks = [t for t in tasks if t.due_date and t.due_date < now and t.status != "completed"]

    return {
        "family": {
            "member_count": len(members),
            "members": [
                {
                    "id": m.id,
                    "name": m.name,
                    "role": m.role,
                    "avatar_url": m.avatar_url,
                    "preferences": _normalize_json_value(m.preferences, {}),
                    "dietary_restrictions": _normalize_json_value(m.dietary_restrictions, []),
                }
                for m in members
            ],
        },
        "tasks": {
            "total": len(tasks),
            "pending": len(pending_tasks),
            "completed": sum(1 for t in tasks if t.status == "completed"),
            "overdue": len(overdue_tasks),
            "recent": [
                {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority, "due_date": t.due_date}
                for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)[:5]
            ],
        },
        "calendar": {
            "upcoming_count": len(upcoming_events),
            "next_events": [
                {"id": e.id, "title": e.title, "start_time": e.start_time, "location": e.location}
                for e in upcoming_events[:5]
            ],
        },
        "reminders": {
            "today_count": len(today_reminders),
            "reminders": [
                {"id": r.id, "title": r.title, "remind_at": r.remind_at}
                for r in today_reminders
            ],
        },
        "grocery": {
            "active_lists": len(active_lists),
            "lists": [{"id": l.id, "name": l.name, "store": l.store} for l in active_lists],
        },
        "agents": {
            "recent_runs": [
                {
                    "id": r.id, "agent_name": r.agent_name, "status": r.status,
                    "duration_ms": r.duration_ms, "started_at": r.started_at,
                }
                for r in recent_runs
            ],
        },
        "emails": {
            "today_count": len(today_emails),
            "important_today_count": len(important_emails),
            "important_today": important_emails,
            "keywords": important_email_keywords(),
        },
        "generated_at": now.isoformat(),
    }


@router.get("/activity-feed")
async def activity_feed(db: AsyncSession = Depends(get_db)):
    from app.db.models import Event
    result = await db.execute(
        select(Event).order_by(Event.created_at.desc()).limit(20)
    )
    events = result.scalars().all()
    return {
        "events": [
            {
                "id": e.id, "type": e.event_type, "source": e.source,
                "payload": e.payload, "created_at": e.created_at,
            }
            for e in events
        ]
    }


@router.get("/health")
async def health():
    resilience = await shared_resilience_health()
    return {
        "status": "healthy",
        "service": "FamilyOps AI",
        "version": settings.app_version,
        "timestamp": datetime.utcnow().isoformat(),
        "shared_resilience_redis": resilience,
    }


@router.get("/version")
async def version():
    versions = prompt_versions()
    return {
        "service": settings.app_name,
        "app_version": settings.app_version,
        "prompt_registry_version": PROMPT_REGISTRY_VERSION,
        "prompt_count": len(versions),
        "prompt_versions": versions,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/metrics")

async def metrics():

    from app.observability.metrics import (
        REQUEST_COUNTER,
        AGENT_COUNTER,
    )

    return {
        "requests":
        REQUEST_COUNTER._value.get(),

        "agents":
        AGENT_COUNTER.collect(),
    }



@router.get("/observability")
async def observability():

    return {
        "tokens": token_tracker.metrics()
    }
