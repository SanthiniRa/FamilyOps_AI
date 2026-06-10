from typing import Dict, Any, Callable, Awaitable
from app.services.rag_service import rag_service
from app.services.web_search_service import web_search_service
from app.services.weather_service import weather_service
from app.services.event_search_service import event_search_service
from app.services.recipe_search_service import recipe_search_service
from app.db.database import AsyncSessionLocal
from app.db.models import CalendarEvent, Task, Email
from sqlalchemy import insert
from datetime import datetime
from app.core.ownership import with_owner_metadata


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
            "web.search": self.search_web,
            "weather.search": self.search_weather,
            "events.search": self.search_events,
            "recipes.search": self.search_recipes,
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
        metadata = dict(payload.get("metadata") or {})
        owner_family_member_id = payload.get("owner_family_member_id") or payload.get("created_by")
        metadata = with_owner_metadata(metadata, owner_family_member_id)

        return await rag_service.search(
            query,
            memory_type=memory_type,
            metadata_filter=metadata or None,
        )

    async def store_memory(self, payload):
        owner_family_member_id = payload.get("owner_family_member_id") or payload.get("created_by")
        return await rag_service.store_memory(
            content=payload["content"],
            memory_type=payload.get("type", "general"),
            metadata=with_owner_metadata(payload.get("metadata"), owner_family_member_id),
        )

    # ======================================================
    # CALENDAR TOOL
    # ======================================================
    async def create_calendar_event(self, payload):
        owner_family_member_id = payload.get("owner_family_member_id") or payload.get("created_by")
        async with AsyncSessionLocal() as db:
            event = CalendarEvent(
                title=payload["title"],
                description=payload.get("description"),
                start_time=datetime.fromisoformat(payload["start_time"]),
                end_time=datetime.fromisoformat(payload["end_time"]),
                location=payload.get("location"),
            )
            if owner_family_member_id:
                event.extra_data = with_owner_metadata(event.extra_data, owner_family_member_id)

            db.add(event)
            await db.commit()
            await db.refresh(event)

            return {"id": event.id, "status": "created"}

    # ======================================================
    # TASK TOOL
    # ======================================================
    async def create_task(self, payload):
        owner_family_member_id = payload.get("owner_family_member_id") or payload.get("created_by")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                insert(Task).values(
                    title=payload["title"],
                    description=payload.get("description"),
                    status="pending",
                    agent_generated=True,
                    created_by=owner_family_member_id,
                    extra_data=with_owner_metadata(payload.get("extra_data"), owner_family_member_id),
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

    # ======================================================
    # WEB SEARCH TOOL
    # ======================================================
    async def search_web(self, payload):
        query = payload["query"]
        max_results = payload.get("max_results")
        fetch_pages = payload.get("fetch_pages", True)
        return await web_search_service.search(
            query=query,
            max_results=max_results,
            fetch_pages=fetch_pages,
        )

    async def search_weather(self, payload):
        return await weather_service.search(
            payload["location"],
            forecast_days=payload.get("forecast_days"),
            country_code=payload.get("country_code"),
        )

    async def search_events(self, payload):
        return await event_search_service.search(
            query=payload.get("query"),
            location=payload.get("location"),
            postal_code=payload.get("postal_code"),
            radius_miles=payload.get("radius_miles"),
            family_friendly=payload.get("family_friendly", True),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            max_results=payload.get("max_results", 10),
        )

    async def search_recipes(self, payload):
        return await recipe_search_service.search(
            payload["query"],
            max_results=payload.get("max_results", 10),
            ingredient=payload.get("ingredient"),
            category=payload.get("category"),
        )


mcp_router = MCPRouter()
