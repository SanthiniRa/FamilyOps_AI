from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.resilience import AsyncTTLCache, RetrySettings, retry_async


class RecipeSearchService:
    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(getattr(settings, "recipe_search_timeout_seconds", 12)))
        self.provider = (getattr(settings, "recipe_search_provider", "themealdb") or "themealdb").strip().lower()
        self.cache_ttl_seconds = max(1, int(getattr(settings, "recipe_search_cache_ttl_seconds", 1800)))
        self.retry_settings = RetrySettings(
            attempts=max(1, int(getattr(settings, "external_api_retry_attempts", 3))),
            base_delay_seconds=float(getattr(settings, "external_api_retry_base_delay_seconds", 0.25)),
            max_delay_seconds=float(getattr(settings, "external_api_retry_max_delay_seconds", 2.0)),
        )
        self.cache = AsyncTTLCache(namespace="recipe-search")

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        ingredient: Optional[str] = None,
        ingredients: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.provider != "themealdb":
            raise ValueError(f"Unsupported recipe provider: {self.provider}")
        normalized_ingredients = self._normalize_ingredients(ingredients)
        if not query and not ingredient and not normalized_ingredients and not category:
            raise ValueError("query, ingredient, or category is required")

        cache_key = "::".join(
            [
                f"query={self._normalize_cache_part(query)}",
                f"ingredient={self._normalize_cache_part(ingredient)}",
                f"ingredients={self._normalize_cache_part(','.join(normalized_ingredients))}",
                f"category={self._normalize_cache_part(category)}",
                f"max={max_results}",
            ]
        )
        meals = await self.cache.get_or_set(
            f"recipes::{cache_key}",
            self.cache_ttl_seconds,
            lambda: self._search_meals(
                query=query,
                ingredient=ingredient,
                ingredients=normalized_ingredients,
                category=category,
            ),
        )
        return {
            "provider": "themealdb",
            "query": query,
            "ingredient": ingredient,
            "ingredients": normalized_ingredients,
            "category": category,
            "results": meals[:max_results],
        }

    async def _search_meals(
        self,
        *,
        query: str,
        ingredient: Optional[str],
        ingredients: Optional[List[str]],
        category: Optional[str],
    ) -> List[Dict[str, Any]]:
        meals: List[Dict[str, Any]] = []

        if ingredients:
            meals = await self._search_by_ingredients(ingredients)

        if query:
            if meals:
                return meals
            meals = await self._search_by_name(query)

        if not meals and ingredient:
            meals = await self._search_by_ingredient(ingredient)

        if not meals and category:
            meals = await self._search_by_category(category)

        return meals

    async def _search_by_name(self, query: str) -> List[Dict[str, Any]]:
        data = await retry_async(
            lambda: self._request_json(
                "https://www.themealdb.com/api/json/v1/1/search.php",
                params={"s": query.strip()},
            ),
            retry_settings=self.retry_settings,
            operation_name="recipe_search",
        )
        return [self._normalize_meal(item) for item in data.get("meals") or []]

    async def _search_by_ingredient(self, ingredient: str) -> List[Dict[str, Any]]:
        data = await retry_async(
            lambda: self._request_json(
                "https://www.themealdb.com/api/json/v1/1/filter.php",
                params={"i": ingredient.strip()},
            ),
            retry_settings=self.retry_settings,
            operation_name="recipe_search",
        )

        meals = data.get("meals") or []
        normalized: List[Dict[str, Any]] = []
        for item in meals[:10]:
            meal_id = item.get("idMeal")
            if meal_id:
                full = await self._lookup_meal(meal_id)
                if full:
                    normalized.append(full)
        return normalized

    async def _search_by_ingredients(self, ingredients: List[str]) -> List[Dict[str, Any]]:
        combined: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for ingredient in ingredients[:5]:
            results = await self._search_by_ingredient(ingredient)
            for meal in results:
                meal_id = str(meal.get("id") or "")
                if not meal_id or meal_id in seen:
                    continue
                seen.add(meal_id)
                combined.append(meal)

        return combined

    async def _search_by_category(self, category: str) -> List[Dict[str, Any]]:
        data = await retry_async(
            lambda: self._request_json(
                "https://www.themealdb.com/api/json/v1/1/filter.php",
                params={"c": category.strip()},
            ),
            retry_settings=self.retry_settings,
            operation_name="recipe_search",
        )

        meals = data.get("meals") or []
        normalized: List[Dict[str, Any]] = []
        for item in meals[:10]:
            meal_id = item.get("idMeal")
            if meal_id:
                full = await self._lookup_meal(meal_id)
                if full:
                    normalized.append(full)
        return normalized

    async def _lookup_meal(self, meal_id: str) -> Optional[Dict[str, Any]]:
        data = await retry_async(
            lambda: self._request_json(
                "https://www.themealdb.com/api/json/v1/1/lookup.php",
                params={"i": meal_id},
            ),
            retry_settings=self.retry_settings,
            operation_name="recipe_lookup",
        )

        meals = data.get("meals") or []
        if not meals:
            return None
        return self._normalize_meal(meals[0])

    async def _request_json(self, url: str, *, params: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    def _normalize_cache_part(self, value: Optional[str]) -> str:
        return (value or "").strip().lower()

    def _normalize_ingredients(self, ingredients: Optional[List[str]]) -> List[str]:
        normalized: List[str] = []
        seen: set[str] = set()
        for ingredient in ingredients or []:
            item = (ingredient or "").strip()
            if not item:
                continue
            lowered = item.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(item)
        return normalized

    def _normalize_meal(self, meal: Dict[str, Any]) -> Dict[str, Any]:
        ingredients = []
        measures = []
        for idx in range(1, 21):
            ingredient = (meal.get(f"strIngredient{idx}") or "").strip()
            measure = (meal.get(f"strMeasure{idx}") or "").strip()
            if ingredient:
                ingredients.append(ingredient)
                if measure:
                    measures.append(f"{measure} {ingredient}".strip())

        return {
            "id": meal.get("idMeal"),
            "name": meal.get("strMeal"),
            "category": meal.get("strCategory"),
            "area": meal.get("strArea"),
            "instructions": meal.get("strInstructions"),
            "thumbnail": meal.get("strMealThumb"),
            "source": meal.get("strSource"),
            "youtube": meal.get("strYoutube"),
            "tags": [tag.strip() for tag in (meal.get("strTags") or "").split(",") if tag.strip()],
            "ingredients": ingredients,
            "ingredient_measures": measures,
        }


recipe_search_service = RecipeSearchService()
