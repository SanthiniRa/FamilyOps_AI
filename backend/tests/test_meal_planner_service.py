import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.meal_planner_service import MealPlanningService  # noqa: E402


class SeededShuffle:
    def __init__(self, seed):
        self.seed = seed

    def shuffle(self, items):
        if not items:
            return

        offset = self.seed % len(items)
        rotated = items[offset:] + items[:offset]
        items[:] = rotated


def _recipe(name: str, tag: str = "vegetarian"):
    return SimpleNamespace(
        id=name.lower(),
        name=name,
        tags=[tag],
        ingredients=[{"name": f"{name} ingredient", "quantity": 1, "unit": "cup", "category": "misc", "price_estimate": 2.5}],
        nutrition={"calories": 100, "protein": 10, "carbs": 20, "fat": 5, "fiber": 3},
    )


def test_generate_plan_varies_by_week_for_recipe_pool(monkeypatch):
    service = MealPlanningService()
    recipes = [_recipe("Recipe A"), _recipe("Recipe B"), _recipe("Recipe C"), _recipe("Recipe D")]

    monkeypatch.setattr(service, "_load_recipes", AsyncMock(return_value=recipes))
    monkeypatch.setattr("app.services.meal_planner_service.random.Random", SeededShuffle)

    async def _run():
        start_one = datetime(2026, 6, 1, tzinfo=timezone.utc)
        start_two = start_one + timedelta(days=7)

        first = await service.generate_plan(
            db=object(),
            week_start=start_one,
            week_end=start_one + timedelta(days=6),
            preferences={},
        )
        second = await service.generate_plan(
            db=object(),
            week_start=start_two,
            week_end=start_two + timedelta(days=6),
            preferences={},
        )

        return first, second

    first, second = asyncio.run(_run())

    assert first["meals"] != second["meals"]


def test_generate_plan_varies_by_week_for_fallback_meals(monkeypatch):
    service = MealPlanningService()

    monkeypatch.setattr(service, "_load_recipes", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.meal_planner_service.random.Random", SeededShuffle)

    async def _run():
        start_one = datetime(2026, 6, 1, tzinfo=timezone.utc)
        start_two = start_one + timedelta(days=7)

        first = await service.generate_plan(
            db=object(),
            week_start=start_one,
            week_end=start_one + timedelta(days=6),
            preferences={"dietary_restrictions": []},
        )
        second = await service.generate_plan(
            db=object(),
            week_start=start_two,
            week_end=start_two + timedelta(days=6),
            preferences={"dietary_restrictions": []},
        )

        return first, second

    first, second = asyncio.run(_run())

    assert first["meals"] != second["meals"]
