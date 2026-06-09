from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, date
from app.db.database import get_db
from app.db.models import Task, CalendarEvent, GroceryList, MealPlan, Reminder, AgentRun, HouseholdMemory, FamilyMember
from app.observability.token_tracker import (
    token_tracker
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _normalize_json_value(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, type(fallback)):
        return value
    return fallback


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    now = datetime.utcnow()
    today_start = datetime.combine(date.today(), datetime.min.time())
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
    return {
        "status": "healthy",
        "service": "FamilyOps AI",
        "version": "1.0.0",
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
