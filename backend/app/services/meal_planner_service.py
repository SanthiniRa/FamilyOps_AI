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

        weekly_additions = self._build_weekly_additions(preferences)
        if weekly_additions:
            meals = self._apply_weekly_additions(meals, weekly_additions)

        grocery_list = self._build_grocery_list(meals, recipes, pantry) if recipes else []
        if weekly_additions:
            grocery_list = self._merge_grocery_items(grocery_list, weekly_additions)

        nutrition = self._calculate_nutrition(recipes, meals)

        cost = self._estimate_cost(grocery_list)

        return {
            "meals": meals,
            "shopping_list": grocery_list,
            "nutrition_summary": nutrition,
            "estimated_cost": cost,
            "over_budget": budget is not None and cost > budget,
            "warnings": warnings,
            "weekly_additions": weekly_additions,
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

    def _build_weekly_additions(self, preferences):
        additions = []
        seen: set[str] = set()
        for item in preferences.get("planned_additions", []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            normalized = self._normalize_name(name)
            if normalized in seen:
                continue
            seen.add(normalized)
            additions.append(
                {
                    "name": name,
                    "quantity": item.get("quantity", 1) or 1,
                    "unit": item.get("unit", "item") or "item",
                    "category": item.get("category", "Snacks") or "Snacks",
                    "price_estimate": item.get("price_estimate", 0) or 0,
                    "notes": item.get("notes"),
                    "source": item.get("source", "memory"),
                    "day": item.get("day"),
                }
            )
        return additions

    def _apply_weekly_additions(self, meals, weekly_additions):
        enriched = {day: dict(day_meals or {}) for day, day_meals in (meals or {}).items()}
        for addition in weekly_additions or []:
            day = str(addition.get("day") or "").strip().lower()
            name = str(addition.get("name") or "").strip()
            if not day or not name:
                continue
            day_meals = enriched.setdefault(day, {})
            existing = day_meals.get("snack")
            if existing:
                if name.lower() not in existing.lower():
                    day_meals["snack"] = f"{existing} / {name}"
            else:
                day_meals["snack"] = name
        return enriched

    def _merge_grocery_items(self, grocery_list, weekly_additions):
        merged = list(grocery_list or [])
        seen = {
            self._normalize_name(str(item.get("name") or ""))
            for item in merged
            if str(item.get("name") or "").strip()
        }

        for addition in weekly_additions or []:
            name = str(addition.get("name") or "").strip()
            if not name:
                continue
            normalized = self._normalize_name(name)
            if normalized in seen:
                continue
            seen.add(normalized)
            merged.append(
                {
                    "name": name,
                    "quantity": addition.get("quantity", 1) or 1,
                    "unit": addition.get("unit", "item") or "item",
                    "category": addition.get("category", "Snacks") or "Snacks",
                    "price_estimate": addition.get("price_estimate", 0) or 0,
                    "notes": addition.get("notes"),
                    "source": addition.get("source", "memory"),
                }
            )

        return merged

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
                if r:
                    n = r.nutrition or {}
                    if not any((n.get("calories"), n.get("protein"), n.get("carbs"), n.get("fat"), n.get("fiber"))):
                        n = self._estimate_recipe_nutrition(r)
                else:
                    n = self._estimate_meal_name_nutrition(str(meal or ""))

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

    def _estimate_recipe_nutrition(self, recipe):
        ingredients = recipe.ingredients or []
        name = self._normalize_name(getattr(recipe, "name", ""))
        servings = getattr(recipe, "servings", None) or 4
        servings = max(1, int(servings))

        total_calories = 0
        protein = 0
        carbs = 0
        fat = 0
        fiber = 0

        for ingredient in ingredients:
            ingredient_name = self._normalize_name(str((ingredient or {}).get("name", "")))
            quantity = ingredient.get("quantity", 1) if isinstance(ingredient, dict) else 1
            quantity = quantity if isinstance(quantity, (int, float)) and quantity > 0 else 1

            ingredient_calories = 60
            ingredient_protein = 2
            ingredient_carbs = 6
            ingredient_fat = 2
            ingredient_fiber = 1

            if any(term in ingredient_name for term in ["chicken", "beef", "pork", "turkey", "fish", "salmon", "tuna", "egg"]):
                ingredient_calories = 140
                ingredient_protein = 14
                ingredient_carbs = 1
                ingredient_fat = 8
            elif any(term in ingredient_name for term in ["rice", "pasta", "bread", "noodle", "potato", "oat", "flour", "tortilla"]):
                ingredient_calories = 110
                ingredient_protein = 3
                ingredient_carbs = 22
                ingredient_fat = 1
                ingredient_fiber = 2
            elif any(term in ingredient_name for term in ["milk", "cheese", "yogurt", "butter", "cream"]):
                ingredient_calories = 90
                ingredient_protein = 5
                ingredient_carbs = 4
                ingredient_fat = 6
            elif any(term in ingredient_name for term in ["beans", "lentil", "chickpea", "peas"]):
                ingredient_calories = 100
                ingredient_protein = 6
                ingredient_carbs = 14
                ingredient_fat = 1
                ingredient_fiber = 4
            elif any(term in ingredient_name for term in ["cake", "cookie", "brownie", "dessert", "ice cream"]):
                ingredient_calories = 180
                ingredient_protein = 2
                ingredient_carbs = 24
                ingredient_fat = 8
            elif any(term in ingredient_name for term in ["oil", "butter", "margarine", "cream"]):
                ingredient_calories = 120
                ingredient_protein = 0
                ingredient_carbs = 0
                ingredient_fat = 14

            total_calories += ingredient_calories * quantity
            protein += ingredient_protein * quantity
            carbs += ingredient_carbs * quantity
            fat += ingredient_fat * quantity
            fiber += ingredient_fiber * quantity

        if not ingredients:
            base = 350
            if any(term in name for term in ["salad", "soup", "stew"]):
                base = 220
            elif any(term in name for term in ["breakfast", "oat", "porridge", "toast"]):
                base = 280
            elif any(term in name for term in ["cake", "cookie", "dessert", "brownie"]):
                base = 260
            total_calories = base
            protein = 12
            carbs = 30
            fat = 12
            fiber = 4

        return {
            "calories": round(total_calories / servings, 2),
            "protein": round(protein / servings, 2),
            "carbs": round(carbs / servings, 2),
            "fat": round(fat / servings, 2),
            "fiber": round(fiber / servings, 2),
        }

    def _estimate_meal_name_nutrition(self, meal_name: str):
        name = self._normalize_name(meal_name)
        base = 320
        protein = 10
        carbs = 35
        fat = 12
        fiber = 4

        if any(term in name for term in ["salad", "soup", "stew", "broth"]):
            base = 220
            protein = 8
            carbs = 18
            fat = 8
            fiber = 5
        elif any(term in name for term in ["breakfast", "oat", "porridge", "toast", "cereal", "yogurt"]):
            base = 280
            protein = 9
            carbs = 32
            fat = 10
            fiber = 5
        elif any(term in name for term in ["pasta", "rice", "bowl", "wrap", "sandwich", "taco", "pizza"]):
            base = 380
            protein = 14
            carbs = 42
            fat = 14
            fiber = 5
        elif any(term in name for term in ["cake", "cookie", "brownie", "dessert", "ice cream", "treat", "sweet"]):
            base = 260
            protein = 3
            carbs = 34
            fat = 11
            fiber = 2
        elif any(term in name for term in ["fish", "salmon", "chicken", "beef", "turkey", "egg", "omelette", "omelet"]):
            base = 420
            protein = 28
            carbs = 12
            fat = 18
            fiber = 3

        return {
            "calories": base,
            "protein": protein,
            "carbs": carbs,
            "fat": fat,
            "fiber": fiber,
        }

    # ================================
    # COST ENGINE
    # ================================
    def _estimate_cost(self, grocery_list):
        return round(
            sum(i.get("price_estimate", 0) for i in grocery_list),
            2
        )

    def _normalize_name(self, value: str) -> str:
        return " ".join((value or "").strip().lower().split())
