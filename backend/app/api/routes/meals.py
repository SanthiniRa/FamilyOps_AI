from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta

from app.db.database import get_db
from app.db.models import MealPlan, Recipe
from app.events.bus import event_bus

# -------------------------
# SAFE PLANNER INIT
# -------------------------
from app.services.meal_planner_service import MealPlanningService

planner = MealPlanningService()

router = APIRouter(prefix="/meals", tags=["meals"])


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
    week_start: datetime
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

@router.get("/plans")
async def list_meal_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MealPlan).order_by(MealPlan.week_start.desc()))
    plans = result.scalars().all()

    return [
        {
            "id": p.id,
            "week_start": p.week_start.isoformat() if p.week_start else None,
            "week_end": p.week_end.isoformat() if p.week_end else None,
            "meals": (p.result or {}).get("meals", p.meals or {}),
            "shopping_list": (p.result or {}).get("shopping_list", []),
            "nutritional_summary": p.nutritional_summary or (p.result or {}).get("nutrition_summary", {}),
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

    week_start = data.week_start.replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=6)

    # 1. preferences
    prefs = await get_household_preferences(db)

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
    nutrition = result.get("nutrition_summary", {})
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
        "nutritional_summary": plan.nutritional_summary or (plan.result or {}).get("nutrition_summary", {}),
        "estimated_cost": (plan.result or {}).get("estimated_cost"),
        "budget": (plan.result or {}).get("budget"),
        "warnings": (plan.result or {}).get("warnings", []),
        "generated_by_ai": plan.generated_by_ai,
    }
