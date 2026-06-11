from typing import Dict, Any, List
from app.services.meal_planner_service import MealPlanningService
from app.services.pantry_service import pantry_service
from app.memory.rag import rag
from app.db.database import AsyncSessionLocal
from app.services.rag_service import rag_service
from app.services.family_preferences import build_meal_memory_hints


def _extract_memory_items(memory_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(memory_context, dict):
        return []

    for key in ("memories", "results", "items"):
        value = memory_context.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


class MealPlanningAgent:

    def __init__(self):
        self.meal_service = MealPlanningService()

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:

        async with AsyncSessionLocal() as db:

            preferences = {
                "dietary_restrictions": state.get("dietary_restrictions", []),
                "dislikes": state.get("family_preferences", {}).get("dislikes", []),
                "vegetarian_days": state.get("metadata", {}).get("vegetarian_days", []),
            }
            preferences.update(build_meal_memory_hints(_extract_memory_items(state.get("memory_context", {}))))

            pantry_items = await pantry_service.get_items(db)

            pantry = [
                {
                    "name": i.name,
                    "quantity": i.quantity,
                    "unit": i.unit,
                }
                for i in pantry_items
            ]

            # -----------------------------
            # CORE MEAL PLAN GENERATION
            # -----------------------------
            plan = await self.meal_service.generate_plan(
                db=db,
                week_start=state["metadata"].get("week_start"),
                week_end=state["metadata"].get("week_end"),
                preferences=preferences,
                budget=state.get("budget"),
                pantry=pantry,
                llm_client=state.get("llm")
            )

            # -----------------------------
            # MEMORY INTEGRATION (STEP 7 FIX)
            # -----------------------------
            await rag_service.store_memory(
                content=f"Meal plan preferences: {preferences}",
                memory_type="meal_preferences",
                metadata={"type": "meal_plan"}
            )

            await rag_service.store_memory(
                content=f"Pantry snapshot: {pantry[:10]}",
                memory_type="pantry_state",
                metadata={"type": "pantry"}
            )

            # -----------------------------
            # RAG CONTEXT ENRICHMENT
            # -----------------------------
            rag_context = await rag.build_context(
                "healthy weekly meal planning nutrition balanced diet"
            )

            return {
                "meal_plan": plan["meals"],
                "shopping_list": plan["shopping_list"],
                "nutrition_summary": plan["nutrition_summary"],
                "estimated_cost": plan["estimated_cost"],
                "rag_context": rag_context,
            }
