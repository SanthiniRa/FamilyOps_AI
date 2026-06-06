from app.db.database import AsyncSessionLocal
from app.db.models import Task, CalendarEvent, Email
from app.services.rag_service import rag_service
from datetime import datetime
from sqlalchemy import insert


class MCPTools:

    # =========================
    # TASK TOOL
    # =========================
    async def create_task(self, data: dict):
        async with AsyncSessionLocal() as db:
            task = Task(
                title=data["title"],
                description=data.get("description"),
                status="pending",
                agent_generated=True,
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return {"task_id": task.id}

    # =========================
    # CALENDAR TOOL
    # =========================
    async def create_event(self, data: dict):
        async with AsyncSessionLocal() as db:
            event = CalendarEvent(
                title=data["title"],
                description=data.get("description"),
                start_time=datetime.fromisoformat(data["start_time"]),
                end_time=datetime.fromisoformat(data["end_time"]),
                location=data.get("location"),
            )
            db.add(event)
            await db.commit()
            await db.refresh(event)
            return {"event_id": event.id}

    # =========================
    # MEMORY TOOL (RAG)
    # =========================
    async def store_memory(self, data: dict):
        return await rag_service.store_memory(
            content=data["content"],
            memory_type=data.get("type", "email")
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
            db.add(email)
            await db.commit()
            return {"status": "stored"}