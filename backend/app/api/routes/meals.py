from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta, date, time, timezone

from app.db.database import get_db
from app.db.models import MealPlan, Recipe
from app.events.bus import event_bus
from app.services.family_preferences import get_household_meal_preferences

# -------------------------
# SAFE PLANNER INIT
# -------------------------
from app.services.meal_planner_service import MealPlanningService

planner = MealPlanningService()

router = APIRouter(prefix="/meals", tags=["meals"])


def _nutrition_template() -> Dict[str, float]:
    return {
        "calories": 0,
        "protein": 0,
        "carbs": 0,
        "fat": 0,
        "fiber": 0,
    }


def _meal_order() -> List[str]:
    return ["breakfast", "lunch", "dinner"]


def _empty_meal_nutrition(meal_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "name": meal_name,
        **_nutrition_template(),
    }


def _empty_day_nutrition() -> Dict[str, Any]:
    return {
        "meals": {meal: _empty_meal_nutrition() for meal in _meal_order()},
        "total": _nutrition_template(),
    }


def _resolve_meal_nutrition(recipe_map: Dict[str, Recipe], meal_name: str) -> Dict[str, float]:
    recipe = recipe_map.get(meal_name)
    if recipe:
        nutrition = recipe.nutrition or {}
        if not any((nutrition.get("calories"), nutrition.get("protein"), nutrition.get("carbs"), nutrition.get("fat"), nutrition.get("fiber"))):
            nutrition = planner._estimate_recipe_nutrition(recipe)
        return {
            "calories": round(float(nutrition.get("calories", 0) or 0), 2),
            "protein": round(float(nutrition.get("protein", 0) or 0), 2),
            "carbs": round(float(nutrition.get("carbs", 0) or 0), 2),
            "fat": round(float(nutrition.get("fat", 0) or 0), 2),
            "fiber": round(float(nutrition.get("fiber", 0) or 0), 2),
        }

    nutrition = planner._estimate_meal_name_nutrition(meal_name)
    return {
        "calories": round(float(nutrition.get("calories", 0) or 0), 2),
        "protein": round(float(nutrition.get("protein", 0) or 0), 2),
        "carbs": round(float(nutrition.get("carbs", 0) or 0), 2),
        "fat": round(float(nutrition.get("fat", 0) or 0), 2),
        "fiber": round(float(nutrition.get("fiber", 0) or 0), 2),
    }


def _add_totals(target: Dict[str, float], nutrition: Dict[str, float]) -> None:
    for key in ("calories", "protein", "carbs", "fat", "fiber"):
        target[key] = round(float(target.get(key, 0) or 0) + float(nutrition.get(key, 0) or 0), 2)


async def _resolve_nutrition_summary(db: AsyncSession, meals: Dict[str, Any], stored_summary: Any) -> Dict[str, Any]:
    if isinstance(stored_summary, dict) and stored_summary.get("days"):
        return stored_summary

    meal_names = [
        str(meal_name).strip()
        for day_meals in (meals or {}).values()
        for meal_name in (day_meals or {}).values()
        if str(meal_name or "").strip()
    ]
    if not meal_names:
        return {
            "days": {},
            "weekly_totals": _nutrition_template(),
            "weekly_average_per_meal": _nutrition_template(),
        }

    result = await db.execute(select(Recipe).where(Recipe.name.in_(meal_names)))
    recipes = result.scalars().all()
    recipe_map = {getattr(r, "name", None): r for r in recipes if getattr(r, "name", None)}

    days: Dict[str, Any] = {}
    weekly_totals = _nutrition_template()
    meal_type_totals = {meal: _nutrition_template() for meal in _meal_order()}
    meal_type_counts = {meal: 0 for meal in _meal_order()}
    meal_count = 0

    for day_name in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]:
        day_meals = (meals or {}).get(day_name, {}) or {}
        day_entry = _empty_day_nutrition()

        for meal_type in _meal_order():
            meal_name = str(day_meals.get(meal_type) or "").strip()
            if not meal_name:
                continue

            nutrition = _resolve_meal_nutrition(recipe_map, meal_name)
            day_entry["meals"][meal_type] = {
                "name": meal_name,
                **nutrition,
            }
            _add_totals(day_entry["total"], nutrition)
            _add_totals(weekly_totals, nutrition)
            _add_totals(meal_type_totals[meal_type], nutrition)
            meal_type_counts[meal_type] += 1
            meal_count += 1

        days[day_name] = day_entry

    meal_type_averages = {
        meal_type: (
            {
                key: round(float(values.get(key, 0) or 0) / meal_type_counts[meal_type], 2)
                for key in ("calories", "protein", "carbs", "fat", "fiber")
            }
            if meal_type_counts[meal_type]
            else _nutrition_template()
        )
        for meal_type, values in meal_type_totals.items()
    }

    weekly_average_per_meal = {
        key: round(float(weekly_totals.get(key, 0) or 0) / meal_count, 2) if meal_count else 0
        for key in ("calories", "protein", "carbs", "fat", "fiber")
    }

    return {
        "days": days,
        "weekly_totals": weekly_totals,
        "weekly_average_per_meal": weekly_average_per_meal,
        "meal_type_averages": meal_type_averages,
    }


# ============================================================
# SCHEMAS
# ============================================================

class RecipeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    ingredients: List[Dict[str, Any]]
    instructions: List[str]
    prep_time: Optional[int] = None
    cook_time: Optional[int] = None
    servings: Optional[int] = None
    cuisine: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    dietary_info: Dict[str, Any] = Field(default_factory=dict)


class MealPlanCreate(BaseModel):
    week_start: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    budget: Optional[float] = None
    pantry_inventory: Dict[str, Any] = Field(default_factory=dict)


# ============================================================
# RECIPES
# ============================================================

@router.get("/recipes", response_model=List[dict])
async def list_recipes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Recipe))
    recipes = result.scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "prep_time": r.prep_time,
            "cook_time": r.cook_time,
            "servings": r.servings,
            "cuisine": r.cuisine,
            "tags": r.tags,
            "dietary_info": r.dietary_info,
            "ingredients": r.ingredients,
            "created_at": r.created_at,
        }
        for r in recipes
    ]


@router.post("/recipes", status_code=201)
async def create_recipe(recipe: RecipeCreate, db: AsyncSession = Depends(get_db)):
    db_recipe = Recipe(**recipe.model_dump())
    db.add(db_recipe)
    await db.commit()
    await db.refresh(db_recipe)

    return {
        "id": db_recipe.id,
        "name": db_recipe.name,
        "created_at": db_recipe.created_at
    }


# ============================================================
# MEAL PLANS
# ============================================================

def _normalize_week_start(value: str) -> datetime:
    try:
        parsed_date = date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="week_start must be an ISO date string (YYYY-MM-DD)",
        ) from exc

    return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)


def _plan_week_start(plan_week_start: datetime) -> datetime:
    if plan_week_start.tzinfo is None:
        return plan_week_start.replace(tzinfo=timezone.utc)
    return plan_week_start.astimezone(timezone.utc)


@router.get("/plans")
async def list_meal_plans(
    week_start: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MealPlan).order_by(MealPlan.week_start.desc(), MealPlan.created_at.desc())
    )
    plans = result.scalars().all()

    if not isinstance(week_start, str):
        week_start = None

    if week_start:
        normalized_week_start = _normalize_week_start(week_start)
        plans = [
            plan
            for plan in plans
            if plan.week_start and _plan_week_start(plan.week_start) == normalized_week_start
        ]

    return [
        {
            "id": p.id,
            "week_start": p.week_start.isoformat() if p.week_start else None,
            "week_end": p.week_end.isoformat() if p.week_end else None,
            "meals": (p.result or {}).get("meals", p.meals or {}),
            "shopping_list": (p.result or {}).get("shopping_list", []),
            "nutritional_summary": await _resolve_nutrition_summary(
                db,
                (p.result or {}).get("meals", p.meals or {}),
                p.nutritional_summary or (p.result or {}).get("nutrition_summary", {})
            ),
            "weekly_additions": (p.result or {}).get("weekly_additions", []),
            "estimated_cost": (p.result or {}).get("estimated_cost"),
            "budget": (p.result or {}).get("budget"),
            "warnings": (p.result or {}).get("warnings", []),
            "created_at": p.created_at,
        }
        for p in plans
    ]


# ============================================================
# SAFE FALLBACK PREFS (NO CRASH EVER)
# ============================================================

async def get_household_preferences(db: AsyncSession):
    try:
        from app.services.family_preferences import get_household_preferences as g
        return await g(db)
    except Exception:
        return {
            "family_size": 0,
            "dietary_restrictions": [],
            "likes": [],
            "dislikes": []
        }


# ============================================================
# AI GENERATION (CRASH PROOF)
# ============================================================

@router.post("/plans/generate")
async def generate_meal_plan(
    data: MealPlanCreate,
    db: AsyncSession = Depends(get_db)
):

    week_start = _normalize_week_start(data.week_start)
    week_end = week_start + timedelta(days=6)

    # 1. preferences
    prefs = await get_household_meal_preferences(db)

    # 2. AI planner (SAFE)
    try:
        result = await planner.generate_plan(
            db=db,
            week_start=week_start,
            week_end=week_end,
            preferences={**prefs, **data.preferences},
            budget=data.budget,
            pantry=data.pantry_inventory
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Planner error: {str(e)}"
        )

    # 3. SAFE OUTPUT NORMALIZATION (CRITICAL)
    meals = result.get("meals", {})
    shopping_list = result.get("shopping_list", [])
    nutrition = await _resolve_nutrition_summary(db, meals, result.get("nutrition_summary", {}))
    cost = result.get("estimated_cost", None)
    warnings = result.get("warnings", [])

    # 4. DB SAVE (must match schema!)
    plan = MealPlan(
        week_start=week_start,
        week_end=week_end,
        meals=meals,
        nutritional_summary=nutrition,
        generated_by_ai=True,
        preferences_used={**prefs, **data.preferences},

        result={
            "meals": meals,
            "shopping_list": shopping_list,
            "nutrition_summary": nutrition,
            "estimated_cost": cost,
            "budget": data.budget,
            "over_budget": result.get("over_budget", False),
            "warnings": warnings,
        }
    )

    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # 5. EVENT
    await event_bus.publish(
        "meal.plan.generated",
        {
            "plan_id": plan.id,
            "week_start": str(week_start),
            "budget": data.budget
        }
    )

    return {
        "id": plan.id,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "meals": meals,
        "shopping_list": shopping_list,
        "nutritional_summary": nutrition,
        "weekly_additions": result.get("weekly_additions", []),
        "estimated_cost": cost,
        "budget": data.budget,
        "over_budget": result.get("over_budget", False),
        "warnings": warnings,
        "generated_by_ai": True
    }


# ============================================================
# GET SINGLE PLAN
# ============================================================

@router.get("/plans/{plan_id}")
async def get_meal_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MealPlan).where(MealPlan.id == plan_id)
    )

    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    return {
        "id": plan.id,
        "week_start": plan.week_start.isoformat() if plan.week_start else None,
        "week_end": plan.week_end.isoformat() if plan.week_end else None,
        "meals": (plan.result or {}).get("meals", plan.meals or {}),
        "shopping_list": (plan.result or {}).get("shopping_list", []),
        "nutritional_summary": await _resolve_nutrition_summary(
            db,
            (plan.result or {}).get("meals", plan.meals or {}),
            plan.nutritional_summary or (plan.result or {}).get("nutrition_summary", {})
        ),
        "weekly_additions": (plan.result or {}).get("weekly_additions", []),
        "estimated_cost": (plan.result or {}).get("estimated_cost"),
        "budget": (plan.result or {}).get("budget"),
        "warnings": (plan.result or {}).get("warnings", []),
        "generated_by_ai": plan.generated_by_ai,
    }
