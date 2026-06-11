import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.family_preferences import build_meal_memory_hints  # noqa: E402
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


def _recipe_without_nutrition(name: str, ingredients=None, tag: str = "vegetarian"):
    return SimpleNamespace(
        id=name.lower(),
        name=name,
        tags=[tag],
        ingredients=ingredients if ingredients is not None else [
            {"name": "Chicken breast", "quantity": 2, "unit": "piece", "category": "meat", "price_estimate": 6},
            {"name": "Rice", "quantity": 1, "unit": "cup", "category": "grains", "price_estimate": 1},
        ],
        nutrition={},
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


def test_build_meal_memory_hints_extracts_saturday_treat():
    hints = build_meal_memory_hints(
        [
            {
                "content": "Add a sweet treat on Saturday for the family.",
                "memory_type": "routine",
            }
        ]
    )

    assert hints["routine_hints"]["saturday"] == ["sweet treat"]
    assert hints["planned_additions"][0]["day"] == "saturday"
    assert hints["planned_additions"][0]["name"] == "sweet treat"


def test_generate_plan_adds_memory_planned_grocery_items(monkeypatch):
    service = MealPlanningService()
    recipes = [_recipe("Recipe A"), _recipe("Recipe B")]

    monkeypatch.setattr(service, "_load_recipes", AsyncMock(return_value=recipes))
    monkeypatch.setattr("app.services.meal_planner_service.random.Random", SeededShuffle)

    async def _run():
        start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = await service.generate_plan(
            db=object(),
            week_start=start,
            week_end=start + timedelta(days=6),
            preferences={
                "planned_additions": [
                    {
                        "day": "saturday",
                        "name": "sweet treat",
                        "category": "Treats",
                        "quantity": 1,
                        "unit": "item",
                        "price_estimate": 0,
                    }
                ]
            },
        )
        return result

    result = asyncio.run(_run())

    assert result["weekly_additions"][0]["name"] == "sweet treat"
    assert any(item["name"] == "sweet treat" for item in result["shopping_list"])
    assert result["meals"]["saturday"]["snack"] == "sweet treat"


def test_generate_plan_estimates_nutrition_when_missing(monkeypatch):
    service = MealPlanningService()
    recipes = [_recipe_without_nutrition("Chicken Rice Bowl")]

    monkeypatch.setattr(service, "_load_recipes", AsyncMock(return_value=recipes))
    monkeypatch.setattr("app.services.meal_planner_service.random.Random", SeededShuffle)

    async def _run():
        start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = await service.generate_plan(
            db=object(),
            week_start=start,
            week_end=start + timedelta(days=6),
            preferences={},
        )
        return result

    result = asyncio.run(_run())

    assert result["nutrition_summary"]["avg_calories"] > 0
    assert result["nutrition_summary"]["avg_protein_g"] > 0


def test_generate_plan_estimates_nutrition_for_fallback_meals(monkeypatch):
    service = MealPlanningService()

    monkeypatch.setattr(service, "_load_recipes", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.services.meal_planner_service.random.Random", SeededShuffle)

    async def _run():
        start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        result = await service.generate_plan(
            db=object(),
            week_start=start,
            week_end=start + timedelta(days=6),
            preferences={"dietary_restrictions": []},
        )
        return result

    result = asyncio.run(_run())

    assert result["nutrition_summary"]["avg_calories"] > 0
    assert result["nutrition_summary"]["avg_protein_g"] > 0
