from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncOpenAI

from app.db.models import GroceryItem, GroceryList, MealPlan
from app.events.bus import event_bus
from app.core.logging import logger
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.services.family_preferences import get_household_preferences
from app.services.meal_planner_service import MealPlanningService
from app.services.openai_utils import (
    is_openai_model_not_found_error,
    openai_chat_model_candidates,
)
from app.core.config import settings


planner = MealPlanningService()

_ALLERGY_EXPANSIONS = {
    "peanut": ["peanut", "peanuts", "peanut butter", "nuts", "almond", "cashew", "walnut", "pecan"],
    "nut": ["nut", "nuts", "almond", "cashew", "walnut", "pecan", "hazelnut"],
    "dairy": ["milk", "cheese", "yogurt", "butter", "cream", "ice cream", "lactose"],
    "lactose": ["milk", "cheese", "yogurt", "butter", "cream", "ice cream", "lactose"],
    "gluten": ["bread", "pasta", "flour", "wheat", "tortilla", "bagel", "cracker", "cereal"],
    "wheat": ["bread", "pasta", "flour", "wheat", "tortilla", "bagel", "cracker", "cereal"],
    "egg": ["egg", "eggs", "mayonnaise", "mayo"],
    "soy": ["soy", "tofu", "edamame", "soy sauce"],
    "fish": ["fish", "salmon", "tuna", "cod", "tilapia", "anchovy"],
    "seafood": ["fish", "shrimp", "crab", "lobster", "salmon", "tuna", "shellfish", "seafood"],
    "shellfish": ["shrimp", "crab", "lobster", "prawn", "shellfish"],
    "sesame": ["sesame", "tahini"],
    "vegetarian": ["chicken", "beef", "pork", "turkey", "salmon", "tuna", "shrimp", "fish", "bacon", "sausage"],
    "vegan": ["milk", "cheese", "yogurt", "butter", "cream", "egg", "eggs", "honey", "chicken", "beef", "pork", "turkey", "fish", "shrimp", "bacon", "sausage"],
}


def _normalize_name(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _unique_preserve_order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    unique: List[Dict[str, Any]] = []
    for item in items:
        name = _normalize_name(str(item.get("name", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(item)
    return unique


def _current_week_start(reference: Optional[datetime] = None) -> datetime:
    now = reference or datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_week_start(reference: Optional[datetime] = None) -> datetime:
    return _current_week_start(reference) + timedelta(days=7)


def _extract_store(message: str) -> Optional[str]:
    lower = message.lower()
    stores = ["walmart", "target", "costco", "kroger", "safeway", "whole foods", "whole_foods", "amazon"]
    for store in stores:
        if store in lower:
            return store.replace("_", " ").title()
    return None


def _create_list_name(message: str, prefix: str) -> str:
    label = "Grocery List" if prefix == "grocery" else "Meal Plan"
    now = datetime.now(timezone.utc).date().isoformat()
    if prefix == "meal" and "next week" in message.lower():
        now = _next_week_start().date().isoformat()
    return f"AI {label} - {now}"


def _is_create_request(message: str, keywords: List[str]) -> bool:
    lower = message.lower()
    create_words = ("create", "make", "generate", "build", "set up", "prep", "prepare")
    return any(word in lower for word in create_words) and any(keyword in lower for keyword in keywords)


def _collect_pantry_inventory(db_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    inventory = db_context.get("pantry_items") or []
    if inventory:
        return inventory
    return db_context.get("pantry_snapshot") or []


def _collect_meal_plan_items(db_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for plan in (db_context.get("meal_plans", []) or []) + (db_context.get("recent_meal_plans", []) or []):
        for item in plan.get("shopping_list", []) or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def _normalize_hint(value: str) -> str:
    return _normalize_name(value).replace("-", " ")


def _extract_household_profile(db_context: Dict[str, Any]) -> Dict[str, Any]:
    family_members = db_context.get("family_members", []) or []
    memories = db_context.get("memories", []) or []

    restrictions: set[str] = set()
    likes: set[str] = set()
    dislikes: set[str] = set()
    memory_highlights: List[str] = []

    for member in family_members:
        for restriction in member.get("dietary_restrictions", []) or []:
            restriction_text = _normalize_hint(str(restriction))
            if restriction_text:
                restrictions.add(restriction_text)
        prefs = member.get("preferences") or {}
        for item in prefs.get("likes", []) or []:
            item_text = _normalize_hint(str(item))
            if item_text:
                likes.add(item_text)
        for item in prefs.get("dislikes", []) or []:
            item_text = _normalize_hint(str(item))
            if item_text:
                dislikes.add(item_text)

    for memory in memories:
        content = str(memory.get("content", "")).strip()
        lowered = _normalize_name(content)
        if not lowered:
            continue
        if any(marker in lowered for marker in ("allerg", "avoid", "can't eat", "cannot eat", "dislike", "prefer", "love", "likes", "loves")):
            memory_highlights.append(content)
        if "allerg" in lowered:
            for token, expansions in _ALLERGY_EXPANSIONS.items():
                if token in lowered:
                    restrictions.update(expansions)

        # Pull out a few obvious food terms from free-form memory notes.
        for token in [
            "peanut", "nuts", "milk", "cheese", "yogurt", "butter", "gluten",
            "wheat", "egg", "eggs", "soy", "fish", "shellfish", "sesame",
            "vegetarian", "vegan", "chicken", "beef", "pork", "turkey",
        ]:
            if token in lowered and ("allerg" in lowered or "avoid" in lowered or "prefer" in lowered or "love" in lowered or "dislike" in lowered):
                restrictions.add(token)

    expanded_restrictions: set[str] = set()
    for restriction in restrictions:
        normalized = _normalize_hint(restriction)
        if not normalized:
            continue
        expanded_restrictions.add(normalized)
        for token, expansions in _ALLERGY_EXPANSIONS.items():
            if token in normalized:
                expanded_restrictions.update(expansions)

    return {
        "restrictions": sorted(expanded_restrictions),
        "likes": sorted(likes),
        "dislikes": sorted(dislikes),
        "memory_highlights": memory_highlights[:8],
    }


def _item_violates_profile(item_name: str, profile: Dict[str, Any]) -> bool:
    normalized = _normalize_hint(item_name)
    for term in profile.get("restrictions", []):
        if not term:
            continue
        if term in normalized or normalized in term:
            return True
    for term in profile.get("dislikes", []):
        if not term:
            continue
        if term in normalized or normalized in term:
            return True
    return False


def _build_grocery_suggestions(db_context: Dict[str, Any], existing_names: set[str]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    household_profile = _extract_household_profile(db_context)

    for item in db_context.get("low_stock_pantry", []):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized = _normalize_name(name)
        if normalized in existing_names:
            continue
        if _item_violates_profile(name, household_profile):
            continue
        quantity = item.get("min_quantity", 1) or 1
        suggestions.append(
            {
                "name": name,
                "category": item.get("category") or "Pantry",
                "quantity": max(1, quantity if isinstance(quantity, (int, float)) else 1),
                "unit": item.get("unit") or "unit",
                "notes": "Low stock in pantry",
            }
        )

    for item in _collect_meal_plan_items(db_context):
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        normalized = _normalize_name(name)
        if normalized in existing_names:
            continue
        if _item_violates_profile(name, household_profile):
            continue
        suggestions.append(
            {
                "name": name,
                "category": item.get("category"),
                "quantity": item.get("quantity", 1) or 1,
                "unit": item.get("unit"),
                "notes": "From recent meal plan",
            }
        )

    fallback = [
        {"name": "Milk", "category": "Dairy", "quantity": 1, "unit": "gallon"},
        {"name": "Eggs", "category": "Dairy", "quantity": 12, "unit": "count"},
        {"name": "Bread", "category": "Bakery", "quantity": 1, "unit": "loaf"},
        {"name": "Chicken Breast", "category": "Meat", "quantity": 2, "unit": "lbs"},
        {"name": "Ground Turkey", "category": "Meat", "quantity": 1, "unit": "lb"},
        {"name": "Spinach", "category": "Produce", "quantity": 1, "unit": "bag"},
        {"name": "Bananas", "category": "Produce", "quantity": 6, "unit": "count"},
        {"name": "Apples", "category": "Produce", "quantity": 6, "unit": "count"},
        {"name": "Tomatoes", "category": "Produce", "quantity": 4, "unit": "count"},
        {"name": "Onions", "category": "Produce", "quantity": 3, "unit": "count"},
        {"name": "Rice", "category": "Pantry", "quantity": 1, "unit": "bag"},
        {"name": "Pasta", "category": "Pantry", "quantity": 2, "unit": "boxes"},
        {"name": "Canned Beans", "category": "Pantry", "quantity": 4, "unit": "cans"},
        {"name": "Peanut Butter", "category": "Pantry", "quantity": 1, "unit": "jar"},
        {"name": "Yogurt", "category": "Dairy", "quantity": 4, "unit": "cups"},
        {"name": "Cheese", "category": "Dairy", "quantity": 1, "unit": "block"},
        {"name": "Coffee", "category": "Beverages", "quantity": 1, "unit": "bag"},
        {"name": "Oatmeal", "category": "Breakfast", "quantity": 1, "unit": "box"},
        {"name": "Tortillas", "category": "Bakery", "quantity": 1, "unit": "pack"},
        {"name": "Potatoes", "category": "Produce", "quantity": 5, "unit": "count"},
    ]
    for item in fallback:
        if _normalize_name(item["name"]) in existing_names:
            continue
        if _item_violates_profile(item["name"], household_profile):
            continue
        suggestions.append(item)

    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in suggestions:
        normalized = _normalize_name(str(item.get("name", "")))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(item)
    return unique[:15]


async def _generate_ai_grocery_suggestions(
    message: str,
    db_context: Dict[str, Any],
    existing_names: set[str],
    target_count: int = 12,
) -> List[Dict[str, Any]]:
    if not settings.openai_api_key:
        return []

    household_profile = _extract_household_profile(db_context)
    prompt = {
        "user_request": message,
        "target_count": target_count,
        "existing_items": sorted(existing_names),
        "low_stock_pantry": db_context.get("low_stock_pantry", []),
        "meal_plans": db_context.get("meal_plans", []) or db_context.get("recent_meal_plans", []),
        "household_profile": household_profile,
        "instructions": (
            "Return a JSON object with key items. "
            "Each item must include name, category, quantity, unit, and notes. "
            "Generate a practical grocery list with variety across produce, dairy, protein, pantry, breakfast, and snacks. "
            "Use household memory, allergies, dislikes, likes, and meal-plan shopping lists to shape the result. "
            "Do not repeat the same items, do not use placeholders, and avoid returning only staples. "
            "Avoid any foods that conflict with restrictions or allergies. "
            f"Return at least {min(target_count, 10)} unique items if possible."
        ),
    }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    last_error: Exception | None = None
    had_success = False
    trace = start_ai_trace(
        "grocery.ai_suggestions",
        input=prompt,
        metadata={
            "target_count": target_count,
            "existing_items_count": len(existing_names),
        },
    )

    for model_name in openai_chat_model_candidates():
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate household grocery suggestions. "
                            "Return JSON only."
                        ),
                    },
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
            )
            raw = response.choices[0].message.content or "{}"
            end_ai_generation(
                trace,
                name="grocery.ai_suggestions",
                model=model_name,
                input=prompt,
                output=raw,
                usage=response.usage.model_dump() if response.usage else None,
                metadata={
                    "target_count": target_count,
                    "existing_items_count": len(existing_names),
                },
            )
            had_success = True
            payload = json.loads(raw)
            items = payload.get("items", [])
            normalized: List[Dict[str, Any]] = []
            seen: set[str] = set()
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                normalized_name = _normalize_name(name)
                if normalized_name in existing_names or normalized_name in seen:
                    continue
                if _item_violates_profile(name, household_profile):
                    continue
                seen.add(normalized_name)
                normalized.append(
                    {
                        "name": name,
                        "category": item.get("category") or "Pantry",
                        "quantity": item.get("quantity", 1) or 1,
                        "unit": item.get("unit") or "unit",
                        "notes": item.get("notes") or "AI suggested item",
                    }
                )
            if normalized:
                return normalized[:target_count]
        except Exception as e:
            last_error = e
            if not is_openai_model_not_found_error(e):
                end_ai_generation(
                    trace,
                    name="grocery.ai_suggestions",
                    model=model_name,
                    input=prompt,
                    output=None,
                    metadata={
                        "target_count": target_count,
                        "existing_items_count": len(existing_names),
                    },
                    level="ERROR",
                    status_message=str(e),
                )
                logger.warning(
                    "agent.grocery.ai_suggestions_failed",
                    model=model_name,
                    error=str(e),
                )
                break

    if had_success:
        return []

    if last_error:
        end_ai_generation(
            trace,
            name="grocery.ai_suggestions",
            model=settings.openai_model,
            input=prompt,
            output=None,
            metadata={
                "target_count": target_count,
                "existing_items_count": len(existing_names),
            },
            level="ERROR",
            status_message=str(last_error),
        )
        logger.info("agent.grocery.ai_suggestions_fallback", error=str(last_error))
    return []


async def create_grocery_list_from_message(
    db: AsyncSession,
    message: str,
    db_context: Dict[str, Any],
) -> Dict[str, Any]:
    list_name = _create_list_name(message, "grocery")
    store = _extract_store(message)
    scheduled_date = datetime.now(timezone.utc)

    grocery_list = GroceryList(
        name=list_name,
        status="active",
        store=store,
        scheduled_date=scheduled_date,
    )
    db.add(grocery_list)
    await db.flush()

    existing_names: set[str] = set()
    for gl in db_context.get("grocery_lists", []):
        for item in gl.get("items", []):
            name = str(item.get("name", "")).strip()
            if name:
                existing_names.add(_normalize_name(name))

    ai_suggestions = await _generate_ai_grocery_suggestions(message, db_context, existing_names, target_count=12)
    suggestions = _unique_preserve_order(ai_suggestions + _build_grocery_suggestions(db_context, existing_names))

    if len(suggestions) < 8:
        supplemental = _build_grocery_suggestions(db_context, existing_names)
        suggestions = _unique_preserve_order(suggestions + supplemental)

    added_items: List[str] = []
    for suggestion in suggestions:
        normalized = _normalize_name(suggestion["name"])
        if normalized in existing_names:
            continue
        db.add(GroceryItem(list_id=grocery_list.id, **suggestion))
        existing_names.add(normalized)
        added_items.append(suggestion["name"])

    await event_bus.publish(
        "grocery.list.created",
        {
            "list_id": grocery_list.id,
            "name": grocery_list.name,
            "item_count": len(added_items),
        },
    )

    logger.info(
        "agent.grocery.created",
        list_id=grocery_list.id,
        item_count=len(added_items),
    )

    return {
        "reply": (
            f"Created grocery list '{grocery_list.name}' with {len(added_items)} items. "
            f"Open the Grocery tab to review it."
        ),
        "resource": {
            "type": "grocery_list",
            "id": grocery_list.id,
            "name": grocery_list.name,
            "item_count": len(added_items),
            "items": added_items,
        },
    }


async def create_meal_plan_from_message(
    db: AsyncSession,
    message: str,
    db_context: Dict[str, Any],
) -> Dict[str, Any]:
    week_start = _next_week_start() if "next week" in message.lower() else _current_week_start()
    if "this week" in message.lower():
        week_start = _current_week_start()
    week_end = week_start + timedelta(days=6)

    prefs = await get_household_preferences(db)
    pantry_inventory = _collect_pantry_inventory(db_context)

    result = await planner.generate_plan(
        db=db,
        week_start=week_start,
        week_end=week_end,
        preferences=prefs,
        pantry=pantry_inventory,
    )

    meals = result.get("meals", {})
    shopping_list = result.get("shopping_list", [])
    nutrition = result.get("nutrition_summary", {})
    cost = result.get("estimated_cost")
    warnings = result.get("warnings", [])

    plan = MealPlan(
        week_start=week_start,
        week_end=week_end,
        meals=meals,
        nutritional_summary=nutrition,
        generated_by_ai=True,
        preferences_used=prefs,
        result={
            "meals": meals,
            "shopping_list": shopping_list,
            "nutrition_summary": nutrition,
            "estimated_cost": cost,
            "over_budget": result.get("over_budget", False),
            "warnings": warnings,
        },
    )
    db.add(plan)
    await db.flush()

    await event_bus.publish(
        "meal.plan.generated",
        {
            "plan_id": plan.id,
            "week_start": week_start.isoformat(),
        },
    )

    logger.info("agent.meal_plan.created", plan_id=plan.id)

    return {
        "reply": (
            f"Created a meal plan for {week_start.date().isoformat()} through {week_end.date().isoformat()}. "
            f"Open the Meals tab to review it."
        ),
        "resource": {
            "type": "meal_plan",
            "id": plan.id,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "shopping_list_count": len(shopping_list),
        },
    }
