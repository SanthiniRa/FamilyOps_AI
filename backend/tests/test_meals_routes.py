import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routes import meals as meal_routes  # noqa: E402


class FakeResult:
    def __init__(self, plans):
        self._plans = plans

    def scalars(self):
        return self

    def all(self):
        return self._plans


def _plan(plan_id: str, week_start: datetime):
    return SimpleNamespace(
        id=plan_id,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        meals={"monday": {"breakfast": f"{plan_id} breakfast"}},
        nutritional_summary={"avg_calories": 0},
        result={
            "meals": {"monday": {"breakfast": f"{plan_id} breakfast"}},
            "shopping_list": [],
            "nutrition_summary": {"avg_calories": 0},
            "estimated_cost": 0,
            "budget": None,
            "warnings": [],
        },
        created_at=week_start,
        generated_by_ai=True,
    )


def test_list_meal_plans_filters_by_selected_week():
    async def _run():
        selected_week = datetime(2026, 6, 1, tzinfo=timezone.utc)
        other_week = selected_week + timedelta(days=7)

        db = SimpleNamespace(
            execute=AsyncMock(
                return_value=FakeResult(
                    [_plan("other", other_week), _plan("match", selected_week)]
                )
            )
        )

        plans = await meal_routes.list_meal_plans(week_start="2026-06-01", db=db)

        assert [plan["id"] for plan in plans] == ["match"]
        assert plans[0]["week_start"] == "2026-06-01T00:00:00+00:00"

    asyncio.run(_run())


def test_generate_meal_plan_accepts_date_only_week_start(monkeypatch):
    async def _run():
        db = SimpleNamespace(
            execute=AsyncMock(return_value=FakeResult([])),
            add=MagicMock(),
            commit=AsyncMock(),
            refresh=AsyncMock(),
        )

        monkeypatch.setattr(
            meal_routes,
            "get_household_preferences",
            AsyncMock(return_value={"dietary_restrictions": []}),
        )
        monkeypatch.setattr(
            meal_routes.planner,
            "generate_plan",
            AsyncMock(
                return_value={
                    "meals": {"monday": {"breakfast": "Oatmeal"}},
                    "shopping_list": [],
                    "nutrition_summary": {"avg_calories": 100},
                    "estimated_cost": 12.5,
                    "over_budget": False,
                    "warnings": [],
                }
            ),
        )
        monkeypatch.setattr(meal_routes.event_bus, "publish", AsyncMock())

        result = await meal_routes.generate_meal_plan(
            meal_routes.MealPlanCreate(week_start="2026-06-01", preferences={}),
            db=db,
        )

        assert result["week_start"] == "2026-06-01T00:00:00+00:00"
        assert result["meals"]["monday"]["breakfast"] == "Oatmeal"
        meal_routes.planner.generate_plan.assert_awaited_once()

    asyncio.run(_run())
