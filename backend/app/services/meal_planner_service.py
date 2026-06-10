from collections import defaultdict
from hashlib import sha256
import random
from typing import List, Dict, Any
from sqlalchemy import select
from app.db.models import Recipe
from app.core.config import settings
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.core.prompt_versioning import prompt_metadata


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
        warnings = []

        filtered = self._filter_recipes(recipes, preferences)
        if recipes and not filtered:
            warnings.append("No recipes matched preferences; using all available recipes.")
            filtered = recipes

        if filtered:
            meals = await self._build_meals(filtered, preferences, llm_client, week_start)
        else:
            warnings.append("No recipes found in the database; generated a fallback meal plan.")
            meals = self._build_fallback_meals(preferences, week_start)

        grocery_list = self._build_grocery_list(meals, recipes, pantry) if recipes else []

        nutrition = self._calculate_nutrition(recipes, meals) if recipes else {
            "avg_calories": 0,
            "avg_protein_g": 0,
            "avg_carbs_g": 0,
            "avg_fat_g": 0,
            "avg_fiber_g": 0,
            "daily_avg_calories": 0,
            "daily_avg_protein_g": 0,
            "daily_avg_carbs_g": 0,
            "daily_avg_fat_g": 0,
            "daily_avg_fiber_g": 0,
        }

        cost = self._estimate_cost(grocery_list)

        return {
            "meals": meals,
            "shopping_list": grocery_list,
            "nutrition_summary": nutrition,
            "estimated_cost": cost,
            "over_budget": budget is not None and cost > budget,
            "warnings": warnings,
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

        filtered = [
            r for r in recipes
            if getattr(r, "ingredients", None) and valid(r)
        ]

        return filtered or [
            r for r in recipes
            if getattr(r, "ingredients", None)
        ]

    # ================================
    # MEAL GENERATION ENGINE
    # ================================
    async def _build_meals(self, recipes, preferences, llm_client, week_start):

        days = [
            "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday"
        ]

        meal_types = ["breakfast", "lunch", "dinner"]

        meals = {}
        used = set()
        week_key = week_start.date().isoformat() if week_start else "unknown-week"
        week_seed = int(sha256(week_key.encode("utf-8")).hexdigest()[:8], 16)
        week_rng = random.Random(week_seed)
        week_pool = list(recipes)
        week_rng.shuffle(week_pool)

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
                        week_pool,
                        preferences,
                        week_key,
                    )
                else:
                    recipe = pick(d_idx * len(meal_types) + m_idx, week_pool)

                meals[day][meal_type] = recipe.name
                used.add(recipe.id)

        return meals

    def _build_fallback_meals(self, preferences, week_start=None):
        vegetarian = "vegetarian" in set(preferences.get("dietary_restrictions", []))

        breakfast_options = [
            "Oatmeal with fruit",
            "Greek yogurt with granola",
            "Eggs and toast",
            "Smoothie bowl",
        ]
        lunch_options = [
            "Vegetable soup and sandwich",
            "Hummus wrap with salad",
            "Pasta salad",
            "Rice bowl with vegetables",
        ]
        dinner_options = [
            "Veggie pasta",
            "Stir-fried vegetables with rice",
            "Bean tacos",
            "Baked potatoes with vegetables",
        ]

        if not vegetarian:
            breakfast_options = [
                "Oatmeal with fruit",
                "Greek yogurt with granola",
                "Eggs and toast",
                "Breakfast burrito",
            ]
            lunch_options = [
                "Chicken salad wrap",
                "Turkey sandwich with fruit",
                "Tuna pasta salad",
                "Grilled cheese and tomato soup",
            ]
            dinner_options = [
                "Chicken stir-fry with rice",
                "Spaghetti with marinara",
                "Taco bowls",
                "Baked salmon with vegetables",
            ]

        week_key = week_start.date().isoformat() if week_start else "unknown-week"
        week_seed = int(sha256(week_key.encode("utf-8")).hexdigest()[:8], 16)
        week_rng = random.Random(week_seed)
        week_rng.shuffle(breakfast_options)
        week_rng.shuffle(lunch_options)
        week_rng.shuffle(dinner_options)

        meals = {}
        days = [
            "monday", "tuesday", "wednesday",
            "thursday", "friday", "saturday", "sunday"
        ]
        for idx, day in enumerate(days):
            meals[day] = {
                "breakfast": breakfast_options[idx % len(breakfast_options)],
                "lunch": lunch_options[idx % len(lunch_options)],
                "dinner": dinner_options[idx % len(dinner_options)],
            }
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
        preferences,
        week_key,
    ):

        prompt = {
            "day": day,
            "meal_type": meal_type,
            "week_key": week_key,
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

        trace = start_ai_trace(
            "meal.plan.recipe_selection",
            input=prompt,
            metadata={
                "day": day,
                "meal_type": meal_type,
                "model": settings.openai_model,
                **prompt_metadata("meal.recipe_selection"),
            },
        )

        try:
            response = await llm.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a meal planning AI. Pick the best recipe and vary choices across weeks."
                    },
                    {
                        "role": "user",
                        "content": str(prompt)
                    }
                ],
                response_format={"type": "json_object"}
            )
        except Exception as exc:
            end_ai_generation(
                trace,
                name="meal.plan.recipe_selection",
                model=settings.openai_model,
                input=prompt,
                output=None,
                metadata={
                    "day": day,
                    "meal_type": meal_type,
                    **prompt_metadata("meal.recipe_selection"),
                },
                level="ERROR",
                status_message=str(exc),
            )
            raise

        data = response.choices[0].message.content
        end_ai_generation(
            trace,
            name="meal.plan.recipe_selection",
            model=settings.openai_model,
            input=prompt,
            output=data,
            usage=response.usage.model_dump() if response.usage else None,
            metadata={
                "day": day,
                "meal_type": meal_type,
                **prompt_metadata("meal.recipe_selection"),
            },
        )

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
            return {
                "avg_calories": 0,
                "avg_protein_g": 0,
                "avg_carbs_g": 0,
                "avg_fat_g": 0,
                "avg_fiber_g": 0,
                "daily_avg_calories": 0,
                "daily_avg_protein_g": 0,
                "daily_avg_carbs_g": 0,
                "daily_avg_fat_g": 0,
                "daily_avg_fiber_g": 0,
            }

        avg_calories = round(total["calories"] / count, 2)
        avg_protein_g = round(total["protein"] / count, 2)
        avg_carbs_g = round(total["carbs"] / count, 2)
        avg_fat_g = round(total["fat"] / count, 2)
        avg_fiber_g = round(total["fiber"] / count, 2)

        return {
            "avg_calories": avg_calories,
            "avg_protein_g": avg_protein_g,
            "avg_carbs_g": avg_carbs_g,
            "avg_fat_g": avg_fat_g,
            "avg_fiber_g": avg_fiber_g,
            "daily_avg_calories": avg_calories,
            "daily_avg_protein_g": avg_protein_g,
            "daily_avg_carbs_g": avg_carbs_g,
            "daily_avg_fat_g": avg_fat_g,
            "daily_avg_fiber_g": avg_fiber_g,
        }

    # ================================
    # COST ENGINE
    # ================================
    def _estimate_cost(self, grocery_list):
        return round(
            sum(i.get("price_estimate", 0) for i in grocery_list),
            2
        )
