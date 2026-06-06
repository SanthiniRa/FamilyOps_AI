from typing import Dict, Any, Callable, Awaitable
from app.services.rag_service import rag_service
from app.db.database import AsyncSessionLocal
from app.db.models import CalendarEvent, Task, Email
from sqlalchemy import insert
from datetime import datetime


class MCPRouter:
    """
    Model Context Protocol Router
    Decides which tool to call based on intent
    """

    def __init__(self):
        self.tools: Dict[str, Callable] = {
            "memory.search": self.search_memory,
            "memory.store": self.store_memory,
            "calendar.create": self.create_calendar_event,
            "task.create": self.create_task,
            "email.store": self.store_email,
        }

    # ======================================================
    # ROUTE REQUEST
    # ======================================================
    async def route(self, action: str, payload: Dict[str, Any]):
        if action not in self.tools:
            raise ValueError(f"Unknown MCP action: {action}")

        return await self.tools[action](payload)

    # ======================================================
    # RAG TOOL
    # ======================================================
    async def search_memory(self, payload):
        query = payload["query"]
        memory_type = payload.get("type")

        return await rag_service.search(query, memory_type=memory_type)

    async def store_memory(self, payload):
        return await rag_service.store_memory(
            content=payload["content"],
            memory_type=payload.get("type", "general"),
            metadata=payload.get("metadata", {})
        )

    # ======================================================
    # CALENDAR TOOL
    # ======================================================
    async def create_calendar_event(self, payload):
        async with AsyncSessionLocal() as db:
            event = CalendarEvent(
                title=payload["title"],
                description=payload.get("description"),
                start_time=datetime.fromisoformat(payload["start_time"]),
                end_time=datetime.fromisoformat(payload["end_time"]),
                location=payload.get("location"),
            )

            db.add(event)
            await db.commit()
            await db.refresh(event)

            return {"id": event.id, "status": "created"}

    # ======================================================
    # TASK TOOL
    # ======================================================
    async def create_task(self, payload):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                insert(Task).values(
                    title=payload["title"],
                    description=payload.get("description"),
                    status="pending",
                    agent_generated=True,
                )
            )
            await db.commit()
            return {"status": "created"}

    # ======================================================
    # EMAIL TOOL
    # ======================================================
    async def store_email(self, payload):
        async with AsyncSessionLocal() as db:
            email = Email(
                message_id=payload["message_id"],
                subject=payload.get("subject"),
                sender=payload.get("sender"),
                body_text=payload.get("body"),
                received_at=datetime.utcnow(),
                processed=True,
            )
            db.add(email)
            await db.commit()
            return {"status": "stored"}


mcp_router = MCPRouter()