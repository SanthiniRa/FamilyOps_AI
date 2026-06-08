from collections import defaultdict
from typing import List, Dict, Any
from sqlalchemy import select
from app.db.models import Recipe


class MealPlanningService:

    # ================================
    # PUBLIC ENTRY POINT
    # ================================
    async def generate_plan(
        self,
        db,
        week_start,
        week_end,
        preferences: Dict[str, Any],
        budget: float | None = None,
        pantry: List[Dict] | None = None,
        llm_client=None
    ):

        recipes = await self._load_recipes(db)

        filtered = self._filter_recipes(recipes, preferences)

        meals = await self._build_meals(filtered, preferences, llm_client)

        grocery_list = self._build_grocery_list(meals, recipes, pantry)

        nutrition = self._calculate_nutrition(recipes, meals)

        cost = self._estimate_cost(grocery_list)

        return {
            "meals": meals,
            "shopping_list": grocery_list,
            "nutrition_summary": nutrition,
            "estimated_cost": cost,
            "over_budget": budget is not None and cost > budget
        }

    # ================================
    # LOAD RECIPES
    # ================================
    async def _load_recipes(self, db):
        result = await db.execute(select(Recipe))
        return result.scalars().all()

    # ================================
    # FILTER ENGINE
    # ================================
    def _filter_recipes(self, recipes, preferences):

        restrictions = set(preferences.get("dietary_restrictions", []))
        dislikes = set(preferences.get("dislikes", []))
        vegetarian_days = set(preferences.get("vegetarian_days", []))

        def valid(recipe, day=None):
            tags = set(recipe.tags or [])

            if restrictions and not restrictions.issubset(tags):
                return False

            if day and day in vegetarian_days and "vegetarian" not in tags:
                return False

            recipe_ingredients = {
                i["name"].lower() for i in (recipe.ingredients or [])
            }

            if recipe_ingredients & dislikes:
                return False

            return True

        # apply basic filtering
        return [
            r for r in recipes
            if getattr(r, "ingredients", None)
        ]

    # ================================
    # MEAL GENERATION ENGINE
    # ================================
    async def _build_meals(self, recipes, preferences, llm_client):

        days = [
            "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday"
        ]

        meal_types = ["breakfast", "lunch", "dinner"]

        meals = {}
        used = set()

        def pick(i, pool):
            return pool[i % len(pool)]

        for d_idx, day in enumerate(days):

            meals[day] = {}

            for m_idx, meal_type in enumerate(meal_types):

                pool = recipes

                if not pool:
                    continue

                if llm_client:
                    recipe = await self._llm_select_recipe(
                        llm_client,
                        day,
                        meal_type,
                        pool,
                        preferences
                    )
                else:
                    recipe = pick(d_idx + m_idx, pool)

                meals[day][meal_type] = recipe.name
                used.add(recipe.id)

        return meals

    # ================================
    # OPTIONAL LLM SELECTION
    # ================================
    async def _llm_select_recipe(
        self,
        llm,
        day,
        meal_type,
        recipes,
        preferences
    ):

        prompt = {
            "day": day,
            "meal_type": meal_type,
            "preferences": preferences,
            "recipes": [
                {
                    "name": r.name,
                    "tags": r.tags,
                    "ingredients": r.ingredients
                }
                for r in recipes[:20]
            ]
        }

        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a meal planning AI. Pick the best recipe."
                },
                {
                    "role": "user",
                    "content": str(prompt)
                }
            ],
            response_format={"type": "json_object"}
        )

        data = response.choices[0].message.content

        import json
        selected = json.loads(data)["recipe_name"]

        return next(r for r in recipes if r.name == selected)

    # ================================
    # GROCERY ENGINE
    # ================================
    def _build_grocery_list(self, meals, recipes, pantry):

        recipe_map = {r.name: r for r in recipes}

        shopping = defaultdict(lambda: {
            "name": "",
            "quantity": 0,
            "unit": "",
            "category": "",
            "price_estimate": 0
        })

        for day in meals.values():
            for meal in day.values():

                recipe = recipe_map.get(meal)
                if not recipe:
                    continue

                for ing in (recipe.ingredients or []):

                    name = ing["name"].lower()

                    shopping[name]["name"] = name
                    shopping[name]["quantity"] += ing.get("quantity", 1)
                    shopping[name]["unit"] = ing.get("unit", "")
                    shopping[name]["category"] = ing.get("category", "misc")
                    shopping[name]["price_estimate"] += ing.get("price_estimate", 0)

        pantry_map = {
            p["name"].lower(): p.get("quantity", 0)
            for p in (pantry or [])
        }

        final = []

        for name, item in shopping.items():

            available = pantry_map.get(name, 0)
            item["quantity"] -= available

            if item["quantity"] > 0:
                final.append(item)

        return final

    # ================================
    # NUTRITION ENGINE
    # ================================
    def _calculate_nutrition(self, recipes, meals):

        recipe_map = {r.name: r for r in recipes}

        total = {
            "calories": 0,
            "protein": 0,
            "carbs": 0,
            "fat": 0,
            "fiber": 0
        }

        count = 0

        for day in meals.values():
            for meal in day.values():

                r = recipe_map.get(meal)
                if not r:
                    continue

                n = r.nutrition or {}

                total["calories"] += n.get("calories", 0)
                total["protein"] += n.get("protein", 0)
                total["carbs"] += n.get("carbs", 0)
                total["fat"] += n.get("fat", 0)
                total["fiber"] += n.get("fiber", 0)

                count += 1

        if count == 0:
            return total

        return {
            "daily_avg_calories": round(total["calories"] / count, 2),
            "daily_avg_protein_g": round(total["protein"] / count, 2),
            "daily_avg_carbs_g": round(total["carbs"] / count, 2),
            "daily_avg_fat_g": round(total["fat"] / count, 2),
            "daily_avg_fiber_g": round(total["fiber"] / count, 2),
        }

    # ================================
    # COST ENGINE
    # ================================
    def _estimate_cost(self, grocery_list):
        return round(
            sum(i.get("price_estimate", 0) for i in grocery_list),
            2
        )