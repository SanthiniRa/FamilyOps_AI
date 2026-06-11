"""
Meal Planning Agent - Dedicated LangGraph Agent

Orchestrates meal planning with advanced capabilities:
- Recipe selection
- Shopping list generation
- Pantry integration
- Nutrition tracking
- Memory-based preferences
- Multi-agent collaboration
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from langchain_core.tools import tool
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.meal_planner_service import MealPlanningService
from app.services.pantry_service import pantry_service
from app.services.shopping_service import shopping_service
from app.agents.knowledge_agent import knowledge_agent
from app.db.database import AsyncSessionLocal
from app.core.logging import logger
from app.services.family_preferences import build_meal_memory_hints


meal_planning_service = MealPlanningService()


def _extract_memory_items(memory_context: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(memory_context, dict):
        return []

    for key in ("memories", "results", "items"):
        value = memory_context.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


# ============================================================
# STRUCTURED TOOLS FOR MEAL PLANNING
# ============================================================

@tool
async def generate_weekly_meal_plan(
    family_preferences: Dict[str, Any],
    budget: Optional[float] = None,
    planning_horizon_days: int = 7,
    use_pantry_inventory: bool = True,
    memory_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a weekly meal plan based on family preferences and budget.
    
    Args:
        family_preferences: Dict with dietary_restrictions, dislikes, vegetarian_days
        budget: Optional budget constraint
        planning_horizon_days: Number of days to plan (default: 7)
        use_pantry_inventory: Whether to account for existing pantry items
        
    Returns:
        Dictionary with meals, shopping_list, nutrition_summary, cost
    """
    try:
        async with AsyncSessionLocal() as db:
            enriched_preferences = dict(family_preferences or {})
            enriched_preferences.update(build_meal_memory_hints(_extract_memory_items(memory_context)))

            # Get pantry if requested
            pantry_items = []
            if use_pantry_inventory:
                pantry_items = await pantry_service.get_items(db)
            
            pantry_dict = pantry_service.get_pantry_dict(pantry_items)
            
            # Calculate week dates
            now = datetime.now(timezone.utc)
            week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=planning_horizon_days - 1)
            
            # Generate plan
            result = await meal_planning_service.generate_plan(
                db=db,
                week_start=week_start,
                week_end=week_end,
                preferences=enriched_preferences,
                budget=budget,
                pantry=pantry_dict,
            )
            
            logger.info(
                "meal.plan.generated",
                budget=budget,
                over_budget=result.get("over_budget", False),
            )
            
            return {
                "success": True,
                "weekly_meal_plan": result.get("meals"),
                "shopping_list": result.get("shopping_list"),
                "nutritional_summary": result.get("nutrition_summary"),
                "estimated_cost": result.get("estimated_cost"),
                "over_budget": result.get("over_budget", False),
            }
    except Exception as e:
        logger.error("meal.plan.generation_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def get_pantry_inventory() -> Dict[str, Any]:
    """
    Get current pantry inventory and alerts.
    
    Returns:
        Dictionary with pantry items, low stock alerts, expiring items
    """
    try:
        async with AsyncSessionLocal() as db:
            items = await pantry_service.get_items(db)
            low_stock = await pantry_service.get_low_stock_items(db)
            expired = await pantry_service.get_expired_items(db)
            summary = await pantry_service.get_pantry_summary(db)
            
            logger.info("meal.pantry.retrieved")
            
            return {
                "success": True,
                "summary": summary,
                "items": [
                    {
                        "name": item.name,
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "category": item.category,
                        "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
                    }
                    for item in items
                ],
                "alerts": {
                    "low_stock_count": len(low_stock),
                    "expiring_soon_count": len(expired),
                }
            }
    except Exception as e:
        logger.error("meal.pantry.retrieval_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def search_recipes(
    query: str,
    dietary_restrictions: Optional[List[str]] = None,
    cuisine: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search for recipes using memory/RAG system.
    
    Args:
        query: Recipe search query
        dietary_restrictions: Filters (vegan, vegetarian, gluten-free, etc.)
        cuisine: Preferred cuisine
        
    Returns:
        List of matching recipes with scores
    """
    try:
        # Use knowledge agent for RAG-based search
        search_context = f"{query}"
        if dietary_restrictions:
            search_context += f" {' '.join(dietary_restrictions)}"
        if cuisine:
            search_context += f" {cuisine}"
        
        results = await knowledge_agent.search(
            query=search_context,
            memory_type="recipe",
            limit=10,
        )
        
        logger.info("meal.recipe.search", query=query, results_count=len(results))
        
        return {
            "success": True,
            "results": results,
        }
    except Exception as e:
        logger.error("meal.recipe.search_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "results": [],
        }


@tool
async def estimate_meal_cost(
    ingredients: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Estimate the cost of a meal based on ingredients.
    
    Args:
        ingredients: List of ingredients with quantity and unit
        
    Returns:
        Dictionary with cost estimate and price breakdown
    """
    try:
        total_cost = sum(
            (ing.get("price_estimate", 0) or 0) * ing.get("quantity", 1)
            for ing in ingredients
        )
        
        logger.info("meal.cost.estimated", total_cost=total_cost)
        
        return {
            "success": True,
            "total_cost": round(total_cost, 2),
            "ingredients_count": len(ingredients),
            "breakdown": [
                {
                    "ingredient": ing.get("name"),
                    "quantity": ing.get("quantity"),
                    "unit": ing.get("unit"),
                    "price_estimate": ing.get("price_estimate"),
                }
                for ing in ingredients
            ]
        }
    except Exception as e:
        logger.error("meal.cost.estimation_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def store_meal_preference(
    meal_name: str,
    rating: int,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store user's meal preference in memory for learning.
    
    Args:
        meal_name: Name of the meal
        rating: User rating (1-5)
        notes: Optional notes about the meal
        
    Returns:
        Confirmation of storage
    """
    try:
        memory_content = f"Meal: {meal_name} | Rating: {rating}/5"
        if notes:
            memory_content += f" | Notes: {notes}"
        
        await knowledge_agent.store(
            content=memory_content,
            memory_type="meal_preference",
            importance=rating,
            tags=["meal_preference", meal_name.lower()],
        )
        
        logger.info("meal.preference.stored", meal_name=meal_name, rating=rating)
        
        return {
            "success": True,
            "meal": meal_name,
            "rating": rating,
            "message": f"Preference for '{meal_name}' (rating: {rating}/5) stored successfully",
        }
    except Exception as e:
        logger.error("meal.preference.storage_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


@tool
async def get_nutrition_summary(
    meal_plan: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    """
    Calculate comprehensive nutrition summary for meal plan.
    
    Args:
        meal_plan: Weekly meal plan with breakfast/lunch/dinner per day
        
    Returns:
        Nutrition summary with daily and weekly totals
    """
    try:
        async with AsyncSessionLocal() as db:
            # Get recipes
            from sqlalchemy import select
            from app.db.models import Recipe
            
            result = await db.execute(select(Recipe))
            recipes = result.scalars().all()
            recipe_map = {r.name: r for r in recipes}
            
            # Calculate nutrition
            daily_nutrition = {}
            weekly_totals = {
                "calories": 0,
                "protein_g": 0,
                "carbs_g": 0,
                "fat_g": 0,
            }
            
            for day, meals in meal_plan.items():
                daily = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
                
                for meal_name in meals.values():
                    recipe = recipe_map.get(meal_name)
                    if recipe and recipe.nutrition:
                        nutrition = recipe.nutrition
                        daily["calories"] += nutrition.get("calories", 0)
                        daily["protein_g"] += nutrition.get("protein", 0)
                        daily["carbs_g"] += nutrition.get("carbs", 0)
                        daily["fat_g"] += nutrition.get("fat", 0)
                
                daily_nutrition[day] = daily
                for key in weekly_totals:
                    weekly_totals[key] += daily[key]
            
            # Calculate averages
            days_count = len(daily_nutrition)
            if days_count > 0:
                for key in weekly_totals:
                    weekly_totals[key] = round(weekly_totals[key] / days_count, 1)
            
            logger.info("meal.nutrition.calculated")
            
            return {
                "success": True,
                "daily_nutrition": daily_nutrition,
                "weekly_average": weekly_totals,
            }
    except Exception as e:
        logger.error("meal.nutrition.calculation_failed", error=str(e))
        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# TOOL REGISTRY
# ============================================================

MEAL_PLANNING_TOOLS = [
    generate_weekly_meal_plan,
    get_pantry_inventory,
    search_recipes,
    estimate_meal_cost,
    store_meal_preference,
    get_nutrition_summary,
]

__all__ = [
    "generate_weekly_meal_plan",
    "get_pantry_inventory",
    "search_recipes",
    "estimate_meal_cost",
    "store_meal_preference",
    "get_nutrition_summary",
    "MEAL_PLANNING_TOOLS",
]
