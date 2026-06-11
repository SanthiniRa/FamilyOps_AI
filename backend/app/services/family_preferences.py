from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from app.db.models import FamilyMember


_MEAL_MEMORY_TYPES = {
    "meal_preference",
    "meal_preferences",
    "preference",
    "routine",
    "household",
}

_DAY_PATTERNS = {
    "monday": re.compile(r"\bmonday\b", re.IGNORECASE),
    "tuesday": re.compile(r"\btuesday\b", re.IGNORECASE),
    "wednesday": re.compile(r"\bwednesday\b", re.IGNORECASE),
    "thursday": re.compile(r"\bthursday\b", re.IGNORECASE),
    "friday": re.compile(r"\bfriday\b", re.IGNORECASE),
    "saturday": re.compile(r"\bsaturday\b", re.IGNORECASE),
    "sunday": re.compile(r"\bsunday\b", re.IGNORECASE),
}

_SPECIAL_ITEM_PATTERNS = [
    (re.compile(r"\bsweet treat\b", re.IGNORECASE), "sweet treat", "Treats"),
    (re.compile(r"\bdessert(s)?\b", re.IGNORECASE), "dessert", "Treats"),
    (re.compile(r"\bcookie(s)?\b", re.IGNORECASE), "cookies", "Treats"),
    (re.compile(r"\bcake\b", re.IGNORECASE), "cake", "Treats"),
    (re.compile(r"\bbrownie(s)?\b", re.IGNORECASE), "brownies", "Treats"),
    (re.compile(r"\bice cream\b", re.IGNORECASE), "ice cream", "Treats"),
    (re.compile(r"\bpancake(s)?\b", re.IGNORECASE), "pancakes", "Breakfast"),
    (re.compile(r"\bpizza\b", re.IGNORECASE), "pizza night", "Dinner"),
]


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def build_meal_memory_hints(memories: List[Dict[str, Any]]) -> Dict[str, Any]:
    planned_additions: List[Dict[str, Any]] = []
    routine_hints: Dict[str, List[str]] = defaultdict(list)
    memory_highlights: List[str] = []

    for memory in memories or []:
        content = str(memory.get("content") or "").strip()
        if not content:
            continue

        lowered = _normalize_text(content)
        memory_type = _normalize_text(str(memory.get("memory_type") or memory.get("category") or ""))

        if memory_type in _MEAL_MEMORY_TYPES or any(pattern.search(content) for pattern, _, _ in _SPECIAL_ITEM_PATTERNS):
            memory_highlights.append(content)

        day_matches = [day for day, pattern in _DAY_PATTERNS.items() if pattern.search(content)]
        if not day_matches:
            continue

        matched_label = ""
        matched_category = "Snacks"
        for pattern, label, category in _SPECIAL_ITEM_PATTERNS:
            if pattern.search(content):
                matched_label = label
                matched_category = category
                break

        if not matched_label:
            if "treat" in lowered:
                matched_label = "sweet treat"
                matched_category = "Treats"
            elif "snack" in lowered:
                matched_label = "snack"
                matched_category = "Snacks"
            else:
                continue

        for day in day_matches:
            if matched_label not in routine_hints[day]:
                routine_hints[day].append(matched_label)
            addition_key = f"{day}:{matched_label}"
            if any(item.get("key") == addition_key for item in planned_additions):
                continue
            planned_additions.append(
                {
                    "key": addition_key,
                    "day": day,
                    "name": matched_label,
                    "category": matched_category,
                    "quantity": 1,
                    "unit": "item",
                    "price_estimate": 0,
                    "notes": content,
                    "source": "memory",
                }
            )

    return {
        "memory_highlights": memory_highlights[:8],
        "routine_hints": dict(routine_hints),
        "planned_additions": planned_additions,
    }


async def get_household_preferences(db):

    result = await db.execute(select(FamilyMember))
    members = result.scalars().all()

    dietary_restrictions = set()
    likes = set()
    dislikes = set()

    for m in members:

        dietary_restrictions.update(
            m.dietary_restrictions or []
        )

        prefs = m.preferences or {}

        likes.update(prefs.get("likes", []))
        dislikes.update(prefs.get("dislikes", []))

    return {
        "family_size": len(members),
        "dietary_restrictions": list(dietary_restrictions),
        "likes": list(likes),
        "dislikes": list(dislikes),
    }


async def get_household_meal_preferences(db, *, memory_limit: int = 40):
    from app.memory.memory import memory_service

    prefs = await get_household_preferences(db)

    try:
        memories = await memory_service.list_memories(limit=memory_limit)
    except Exception:
        memories = []

    hints = build_meal_memory_hints(memories)
    prefs.update(hints)
    return prefs
