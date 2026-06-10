import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routes.calendar import CalendarEventCreate, create_event  # noqa: E402
from app.api.routes.memory import MemoryCreate, create_memory  # noqa: E402
from app.api.routes.reminders import ReminderCreate, create_reminder  # noqa: E402
from app.api.routes.tasks import TaskCreate, create_task  # noqa: E402
from app.core.ownership import metadata_matches_owner, with_owner_metadata  # noqa: E402


def test_owner_metadata_helpers_keep_legacy_items_visible():
    metadata = with_owner_metadata({"tags": ["school"]}, "family-1")
    assert metadata["owner_family_member_id"] == "family-1"
    overwritten = with_owner_metadata({"owner_family_member_id": "family-9"}, "family-1")
    assert overwritten["owner_family_member_id"] == "family-1"
    assert metadata_matches_owner(metadata, "family-1")
    assert metadata_matches_owner({"tags": ["legacy"]}, "family-1")
    assert not metadata_matches_owner({"owner_family_member_id": "family-2"}, "family-1")


def test_create_task_assigns_created_by_from_current_user(monkeypatch):
    async def _run():
        db = MagicMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        monkeypatch.setattr("app.api.routes.tasks.event_bus.publish", AsyncMock())

        user = SimpleNamespace(family_member_id="family-1")
        await create_task(
            TaskCreate(title="Pack lunch"),
            db=db,
            current_user=user,
        )

        task = db.add.call_args.args[0]
        assert task.created_by == "family-1"
        assert task.extra_data["owner_family_member_id"] == "family-1"

    asyncio.run(_run())


def test_create_reminder_defaults_to_current_user_member(monkeypatch):
    async def _run():
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        monkeypatch.setattr("app.api.routes.reminders.event_bus.publish", AsyncMock())

        user = SimpleNamespace(family_member_id="family-2")
        await create_reminder(
            ReminderCreate(
                title="Pay school fee",
                remind_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            ),
            db=db,
            current_user=user,
        )

        reminder = db.add.call_args.args[0]
        assert reminder.member_id == "family-2"
        assert reminder.extra_data["owner_family_member_id"] == "family-2"

    asyncio.run(_run())


def test_create_event_tags_owner_metadata(monkeypatch):
    async def _run():
        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        monkeypatch.setattr("app.api.routes.calendar.event_bus.publish", AsyncMock())

        user = SimpleNamespace(family_member_id="family-3")
        await create_event(
            CalendarEventCreate(
                title="Dentist appointment",
                start_time=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc),
            ),
            db=db,
            current_user=user,
        )

        event = db.add.call_args.args[0]
        assert event.extra_data["owner_family_member_id"] == "family-3"

    asyncio.run(_run())


def test_create_memory_stores_owner_metadata(monkeypatch):
    async def _run():
        from app.api.routes import memory as memory_route

        monkeypatch.setattr(
            memory_route.memory_service,
            "create_memory",
            AsyncMock(
                return_value=SimpleNamespace(
                    id="mem-1",
                    content="Hello",
                    memory_type="general",
                    memory_metadata={"owner_family_member_id": "family-4", "tags": ["home"]},
                    created_at="2026-06-10T12:00:00Z",
                    updated_at="2026-06-10T12:00:00Z",
                )
            )
        )

        user = SimpleNamespace(family_member_id="family-4")
        await create_memory(
            MemoryCreate(content="Hello", tags=["home"]),
            current_user=user,
        )

        call_kwargs = memory_route.memory_service.create_memory.call_args.kwargs
        assert call_kwargs["metadata"]["owner_family_member_id"] == "family-4"

    asyncio.run(_run())
