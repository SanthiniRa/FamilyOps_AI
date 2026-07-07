from typing import Optional

from app.db.database import AsyncSessionLocal
from app.db.models import Task, CalendarEvent, Email
from app.services.rag_service import rag_service
from datetime import datetime, date, time, timezone
from sqlalchemy import insert
from app.observability.metrics import TOOL_COUNTER
from app.core.ownership import with_owner_metadata

class MCPTools:

    def _owner_family_member_id(self, data: dict) -> Optional[str]:
        return data.get("owner_family_member_id") or data.get("created_by")

    def _normalize_due_date(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time(9, 0), tzinfo=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                try:
                    parsed_date = date.fromisoformat(value)
                    return datetime.combine(parsed_date, time(9, 0), tzinfo=timezone.utc)
                except ValueError:
                    return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        return None

    # =========================
    # TASK TOOL
    # =========================
    async def create_task(self, data: dict):
        owner_family_member_id = self._owner_family_member_id(data)
        async with AsyncSessionLocal() as db:
            task = Task(
                title=data["title"],
                description=data.get("description"),
                due_date=self._normalize_due_date(data.get("due_date")),
                priority=data.get("priority", "medium"),
                status=data.get("status", "pending"),
                agent_generated=True,
                created_by=owner_family_member_id,
                tags=data.get("tags", []),
                extra_data=with_owner_metadata(data.get("extra_data"), owner_family_member_id),
            )
            TOOL_COUNTER.labels(
                tool="create_task"
            ).inc()
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return {"task_id": task.id}

    # =========================
    # CALENDAR TOOL
    # =========================
    async def create_event(self, data: dict):
        owner_family_member_id = self._owner_family_member_id(data)
        async with AsyncSessionLocal() as db:
            event = CalendarEvent(
                title=data["title"],
                description=data.get("description"),
                start_time=datetime.fromisoformat(data["start_time"]),
                end_time=datetime.fromisoformat(data["end_time"]),
                location=data.get("location"),
            )
            if owner_family_member_id:
                event.extra_data = with_owner_metadata(event.extra_data, owner_family_member_id)
            TOOL_COUNTER.labels(
                tool="create_event"
            ).inc()
            db.add(event)
            await db.commit()
            await db.refresh(event)
            return {"event_id": event.id}

    # =========================
    # MEMORY TOOL (RAG)
    # =========================
    async def store_memory(self, data: dict):
        owner_family_member_id = self._owner_family_member_id(data)
        TOOL_COUNTER.labels(
                tool="store_memory"
            ).inc()
        return await rag_service.store_memory(
            content=data["content"],
            memory_type=data.get("type", "email"),
            metadata=with_owner_metadata(data.get("metadata"), owner_family_member_id),
        )

    # =========================
    # EMAIL TOOL
    # =========================
    async def store_email(self, data: dict):
        async with AsyncSessionLocal() as db:
            email = Email(
                message_id=data["message_id"],
                subject=data.get("subject"),
                sender=data.get("sender"),
                body_text=data.get("body"),
                received_at=datetime.utcnow(),
                processed=True,
            )
            TOOL_COUNTER.labels(
                tool="store_email"
            ).inc()
            db.add(email)
            await db.commit()
            return {"status": "stored"}
