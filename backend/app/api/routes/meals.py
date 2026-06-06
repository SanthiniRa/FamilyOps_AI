from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional, Dict
from pydantic import BaseModel
from datetime import datetime, timedelta
from app.db.database import get_db
from app.db.models import MealPlan, Recipe
from app.events.bus import event_bus

router = APIRouter(prefix="/meals", tags=["meals"])


class RecipeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    ingredients: List[Dict]
    instructions: List[str]
    prep_time: Optional[int] = None
    cook_time: Optional[int] = None
    servings: Optional[int] = None
    cuisine: Optional[str] = None
    tags: List[str] = []
    dietary_info: Dict = {}


class MealPlanCreate(BaseModel):
    week_start: datetime
    preferences: Dict = {}


@router.get("/recipes", response_model=List[dict])
async def list_recipes(
    cuisine: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    q = select(Recipe)
    result = await db.execute(q)
    recipes = result.scalars().all()
    return [
        {
            "id": r.id, "name": r.name, "description": r.description,
            "prep_time": r.prep_time, "cook_time": r.cook_time,
            "servings": r.servings, "cuisine": r.cuisine,
            "tags": r.tags, "dietary_info": r.dietary_info,
            "ingredients": r.ingredients, "created_at": r.created_at,
        }
        for r in recipes
    ]


@router.post("/recipes", status_code=201)
async def create_recipe(recipe: RecipeCreate, db: AsyncSession = Depends(get_db)):
    db_recipe = Recipe(**recipe.model_dump())
    db.add(db_recipe)
    await db.commit()
    return {"id": db_recipe.id, "name": db_recipe.name, "created_at": db_recipe.created_at}


@router.get("/plans")
async def list_meal_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MealPlan).order_by(MealPlan.week_start.desc()))
    plans = result.scalars().all()
    return [
        {
            "id": p.id, "week_start": p.week_start.date().isoformat(), "week_end": p.week_end,
            "meals": p.meals, "generated_by_ai": p.generated_by_ai,
            "nutritional_summary": p.nutritional_summary, "created_at": p.created_at,
        }
        for p in plans
    ]


@router.post("/plans/generate")
async def generate_meal_plan(data: MealPlanCreate, db: AsyncSession = Depends(get_db)):
    week_start = data.week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=6)

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    meal_types = ["breakfast", "lunch", "dinner"]

    sample_meals = {
        "breakfast": ["Oatmeal with berries", "Scrambled eggs & toast", "Greek yogurt parfait",
                      "Avocado toast", "Smoothie bowl", "Pancakes", "Fruit salad"],
        "lunch": ["Chicken salad wrap", "Tomato soup & grilled cheese", "Buddha bowl",
                  "Turkey sandwich", "Caesar salad", "Lentil soup", "Quinoa bowl"],
        "dinner": ["Pasta bolognese", "Grilled salmon & veggies", "Chicken stir fry",
                   "Beef tacos", "Vegetable curry", "Baked chicken thighs", "Shrimp fried rice"],
    }

    meals = {}
    for i, day in enumerate(days):
        meals[day] = {
            meal_type: sample_meals[meal_type][i]
            for meal_type in meal_types
        }

    existing = await db.execute(
        select(MealPlan).where(MealPlan.week_start == week_start)
    )

    existing_plan = existing.scalar_one_or_none()

    if existing_plan:
        return {
            "id": existing_plan.id,
            "week_start": existing_plan.week_start,
            "week_end": existing_plan.week_end,
            "meals": existing_plan.meals,
            "nutritional_summary": existing_plan.nutritional_summary,
            "generated_by_ai": existing_plan.generated_by_ai,
        }

    plan = MealPlan(
        week_start=week_start,
        week_end=week_end,
        meals=meals,
        generated_by_ai=True,
        preferences_used=data.preferences,
        nutritional_summary={
            "avg_calories": 1850,
            "avg_protein_g": 85,
            "avg_carbs_g": 220,
            "avg_fat_g": 65,
        },
    )

    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    await event_bus.publish("meal.plan.generated", {"plan_id": plan.id, "week_start": str(week_start)})

    return {
        "id": plan.id,
        "week_start": plan.week_start,
        "week_end": plan.week_end,
        "meals": plan.meals,
        "nutritional_summary": plan.nutritional_summary,
        "generated_by_ai": True,
    }


@router.get("/plans/{plan_id}")
async def get_meal_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MealPlan).where(MealPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return {
        "id": plan.id, "week_start": plan.week_start, "week_end": plan.week_end,
        "meals": plan.meals, "generated_by_ai": plan.generated_by_ai,
        "nutritional_summary": plan.nutritional_summary,
    }
