from pydantic import BaseModel
from typing import List, Dict, Any


class MealPlanResult(BaseModel):
    weekly_meal_plan: dict
    shopping_list: list
    nutritional_summary: dict
    estimated_cost: float
    pantry_items_used: list
    pantry_items_to_purchase: list
    recommendations: list