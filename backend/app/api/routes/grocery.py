import json
import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import datetime

from openai import AsyncOpenAI

from app.core.config import settings
from app.observability.langfuse_client import start_ai_trace, end_ai_generation
from app.db.database import get_db
from app.db.models import GroceryList, GroceryItem, PantryItem, MealPlan, Memory, FamilyMember
from app.events.bus import event_bus
from app.services.pantry_service import pantry_service

router = APIRouter(prefix="/grocery", tags=["grocery"])


class GroceryListCreate(BaseModel):
    name: str
    store: Optional[str] = None
    scheduled_date: Optional[datetime] = None


class GroceryItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    quantity: float = 1
    unit: Optional[str] = None
    notes: Optional[str] = None
    price_estimate: Optional[float] = None


class GroceryItemUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[float] = None
    checked: Optional[bool] = None
    category: Optional[str] = None
    price_estimate: Optional[float] = None


class GroceryListResponse(BaseModel):
    id: str
    name: str
    status: str
    store: Optional[str]
    scheduled_date: Optional[datetime]
    total_estimate: Optional[float]
    created_at: datetime
    items: List[dict] = []

    class Config:
        from_attributes = True


def _normalize_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _unique_preserve_order(items: List[dict]) -> List[dict]:
    seen: set[str] = set()
    unique_items: List[dict] = []
    for item in items:
        name = _normalize_name(str(item.get("name", "")))
        if not name or name in seen:
            continue
        seen.add(name)
        unique_items.append(item)
    return unique_items


def _meal_plan_summary(plan: MealPlan) -> dict:
    result = plan.result or {}
    meals = result.get("meals") or plan.meals or {}
    shopping_list = result.get("shopping_list") or []
    return {
        "week_start": plan.week_start.isoformat() if plan.week_start else None,
        "week_end": plan.week_end.isoformat() if plan.week_end else None,
        "meals": meals,
        "shopping_list": shopping_list,
    }


async def _build_household_context(db: AsyncSession) -> dict:
    low_stock_items = await pantry_service.get_low_stock_items(db)
    expiring_items = await pantry_service.get_expired_items(db)

    low_stock = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "min_quantity": item.min_quantity,
            "unit": item.unit,
            "category": item.category,
            "notes": item.notes,
        }
        for item in low_stock_items[:10]
    ]

    expiring = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
            "category": item.category,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
        }
        for item in expiring_items[:10]
    ]

    plans_result = await db.execute(
        select(MealPlan).order_by(MealPlan.week_start.desc()).limit(3)
    )
    plans = plans_result.scalars().all()
    recent_plans = [_meal_plan_summary(plan) for plan in plans]

    pantry_result = await db.execute(
        select(PantryItem).order_by(PantryItem.category, PantryItem.name).limit(40)
    )
    pantry_items = pantry_result.scalars().all()
    pantry_snapshot = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "unit": item.unit,
            "category": item.category,
        }
        for item in pantry_items
    ]

    memories_result = await db.execute(
        select(Memory).order_by(Memory.created_at.desc()).limit(10)
    )
    memories = memories_result.scalars().all()

    members_result = await db.execute(select(FamilyMember))
    members = members_result.scalars().all()

    return {
        "low_stock": low_stock,
        "expiring_soon": expiring,
        "recent_meal_plans": recent_plans,
        "pantry_snapshot": pantry_snapshot,
        "memories": [
            {
                "id": m.id,
                "content": m.content,
                "memory_type": m.memory_type,
                "tags": (m.memory_metadata or {}).get("tags", []),
            }
            for m in memories
        ],
        "family_members": [
            {
                "id": member.id,
                "name": member.name,
                "dietary_restrictions": member.dietary_restrictions or [],
                "likes": (member.preferences or {}).get("likes", []),
                "dislikes": (member.preferences or {}).get("dislikes", []),
            }
            for member in members
        ],
    }


def _fallback_suggestions(existing_names: set[str], list_name: str, store: Optional[str]) -> List[dict]:
    name_hint = f"{list_name} at {store}" if store else list_name
    pantry_pools = [
        {"name": "Milk", "category": "Dairy", "quantity": 1, "unit": "gallon"},
        {"name": "Eggs", "category": "Dairy", "quantity": 12, "unit": "count"},
        {"name": "Butter", "category": "Dairy", "quantity": 1, "unit": "stick"},
        {"name": "Yogurt", "category": "Dairy", "quantity": 4, "unit": "cups"},
        {"name": "Bread", "category": "Bakery", "quantity": 1, "unit": "loaf"},
        {"name": "Bagels", "category": "Bakery", "quantity": 1, "unit": "pack"},
        {"name": "Chicken Breast", "category": "Meat", "quantity": 2, "unit": "lbs"},
        {"name": "Ground Turkey", "category": "Meat", "quantity": 1, "unit": "lb"},
        {"name": "Salmon Fillet", "category": "Seafood", "quantity": 2, "unit": "lbs"},
        {"name": "Spinach", "category": "Produce", "quantity": 1, "unit": "bag"},
        {"name": "Bananas", "category": "Produce", "quantity": 6, "unit": "count"},
        {"name": "Apples", "category": "Produce", "quantity": 6, "unit": "count"},
        {"name": "Tomatoes", "category": "Produce", "quantity": 4, "unit": "count"},
        {"name": "Onions", "category": "Produce", "quantity": 3, "unit": "count"},
        {"name": "Rice", "category": "Pantry", "quantity": 1, "unit": "bag"},
        {"name": "Pasta", "category": "Pantry", "quantity": 2, "unit": "boxes"},
        {"name": "Canned Beans", "category": "Pantry", "quantity": 4, "unit": "cans"},
        {"name": "Peanut Butter", "category": "Pantry", "quantity": 1, "unit": "jar"},
        {"name": "Coffee", "category": "Beverages", "quantity": 1, "unit": "bag"},
        {"name": "Sparkling Water", "category": "Beverages", "quantity": 1, "unit": "case"},
    ]

    suggestions: List[dict] = []
    for item in pantry_pools:
        if _normalize_name(item["name"]) in existing_names:
            continue
        suggestions.append(item)
        if len(suggestions) >= 8:
            break

    if not suggestions:
        suggestions = [
            {"name": f"{name_hint} staples", "category": "Pantry", "quantity": 1, "unit": "list"},
            {"name": f"{name_hint} fruit", "category": "Produce", "quantity": 1, "unit": "bag"},
            {"name": f"{name_hint} protein", "category": "Protein", "quantity": 1, "unit": "pack"},
            {"name": f"{name_hint} breakfast items", "category": "Breakfast", "quantity": 1, "unit": "batch"},
        ]

    return suggestions


async def _generate_ai_suggestions(
    db: AsyncSession,
    gl: GroceryList,
    existing_names: set[str],
) -> List[dict]:
    household_context = await _build_household_context(db)
    prompt = {
        "list_name": gl.name,
        "store": gl.store,
        "scheduled_date": gl.scheduled_date.isoformat() if gl.scheduled_date else None,
        "existing_items": sorted(existing_names),
        "household_context": household_context,
        "task": (
            "Suggest 8 to 10 practical grocery items that are not already on the list. "
            "Prioritize low-stock pantry items and items from recent meal-plan shopping lists. "
            "Avoid duplicates, keep items concrete, and prefer items that fit the list name and store. "
            "Return JSON with a single key 'items' containing an array of objects with "
            "name, category, quantity, unit, and notes."
        ),
    }

    base_suggestions: List[dict] = []
    try:
        if settings.openai_api_key:
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            trace = start_ai_trace(
                "grocery.list_suggestions",
                input=prompt,
                metadata={"list_name": gl.name, "store": gl.store},
            )
            try:
                response = await client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You help families build useful grocery lists. "
                                "Use the provided pantry and meal-plan context. "
                                "Avoid duplicates, keep items concrete, and return JSON only."
                            ),
                        },
                        {"role": "user", "content": json.dumps(prompt)},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.8,
                )
            except Exception as exc:
                end_ai_generation(
                    trace,
                    name="grocery.list_suggestions",
                    model=settings.openai_model,
                    input=prompt,
                    output=None,
                    metadata={"list_name": gl.name, "store": gl.store},
                    level="ERROR",
                    status_message=str(exc),
                )
                raise

            raw = response.choices[0].message.content or "{}"
            end_ai_generation(
                trace,
                name="grocery.list_suggestions",
                model=settings.openai_model,
                input=prompt,
                output=raw,
                usage=response.usage.model_dump() if response.usage else None,
                metadata={"list_name": gl.name, "store": gl.store},
            )
            payload = json.loads(raw)
            items = payload.get("items", [])
            normalized: List[dict] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                if _normalize_name(name) in existing_names:
                    continue
                normalized.append(
                    {
                        "name": name,
                        "category": item.get("category"),
                        "quantity": item.get("quantity", 1) or 1,
                        "unit": item.get("unit"),
                        "notes": item.get("notes"),
                        "price_estimate": item.get("price_estimate"),
                    }
                )

            base_suggestions = _unique_preserve_order(normalized)
    except Exception:
        base_suggestions = []

    if not base_suggestions:
        base_suggestions = _fallback_suggestions(existing_names, gl.name, gl.store)

    context_items: List[dict] = []
    for item in household_context.get("low_stock", []):
        normalized_name = _normalize_name(item["name"])
        if normalized_name in existing_names:
            continue
        needed_qty = math.ceil(max(0.0, float(item.get("min_quantity", 1)) - float(item.get("quantity", 0))))
        context_items.append(
            {
                "name": item["name"],
                "category": item.get("category") or "Pantry",
                "quantity": max(1, int(needed_qty) if needed_qty else 1),
                "unit": item.get("unit"),
                "notes": "Low stock in pantry",
            }
        )

    for plan in household_context.get("recent_meal_plans", []):
        for item in plan.get("shopping_list", []):
            name = str(item.get("name", "")).strip()
            if not name or _normalize_name(name) in existing_names:
                continue
            context_items.append(
                {
                    "name": name,
                    "category": item.get("category"),
                    "quantity": item.get("quantity", 1) or 1,
                    "unit": item.get("unit"),
                    "notes": "From recent meal plan",
                }
            )

    combined = _unique_preserve_order(context_items + base_suggestions)
    return combined[:10]


@router.get("/lists", response_model=List[GroceryListResponse])
async def list_grocery_lists(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(GroceryList).order_by(GroceryList.created_at.desc())
    )
    lists = result.scalars().all()
    response = []
    for gl in lists:
        items_result = await db.execute(select(GroceryItem).where(GroceryItem.list_id == gl.id))
        items = items_result.scalars().all()
        response.append({
            "id": gl.id,
            "name": gl.name,
            "status": gl.status,
            "store": gl.store,
            "scheduled_date": gl.scheduled_date,
            "total_estimate": gl.total_estimate,
            "created_at": gl.created_at,
            "items": [{"id": i.id, "name": i.name, "quantity": i.quantity,
                       "unit": i.unit, "checked": i.checked, "category": i.category} for i in items],
        })
    return response


@router.post("/lists", status_code=201)
async def create_grocery_list(data: GroceryListCreate, db: AsyncSession = Depends(get_db)):
    gl = GroceryList(**data.model_dump())
    db.add(gl)
    await db.commit()
    await db.refresh(gl)
    await event_bus.publish("grocery.list.created", {"list_id": gl.id, "name": gl.name})
    return {"id": gl.id, "name": gl.name, "status": gl.status, "created_at": gl.created_at}


@router.get("/lists/{list_id}")
async def get_grocery_list(list_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroceryList).where(GroceryList.id == list_id))
    gl = result.scalar_one_or_none()
    if not gl:
        raise HTTPException(status_code=404, detail="Grocery list not found")
    items_result = await db.execute(select(GroceryItem).where(GroceryItem.list_id == list_id))
    items = items_result.scalars().all()
    return {
        "id": gl.id, "name": gl.name, "status": gl.status, "store": gl.store,
        "scheduled_date": gl.scheduled_date, "total_estimate": gl.total_estimate,
        "created_at": gl.created_at,
        "items": [{"id": i.id, "name": i.name, "quantity": i.quantity,
                   "unit": i.unit, "checked": i.checked, "category": i.category,
                   "price_estimate": i.price_estimate, "notes": i.notes} for i in items],
    }


@router.post("/lists/{list_id}/items", status_code=201)
async def add_item(list_id: str, item: GroceryItemCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroceryList).where(GroceryList.id == list_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Grocery list not found")
    db_item = GroceryItem(list_id=list_id, **item.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    await event_bus.publish("grocery.item.added", {"item_id": db_item.id, "list_id": list_id})
    return {"id": db_item.id, "name": db_item.name, "quantity": db_item.quantity}


@router.patch("/items/{item_id}")
async def update_item(item_id: str, update: GroceryItemUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    return {"id": item.id, "name": item.name, "checked": item.checked}


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroceryItem).where(GroceryItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)


@router.post("/lists/{list_id}/generate-ai")
async def generate_grocery_list_ai(list_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GroceryList).where(GroceryList.id == list_id))
    gl = result.scalar_one_or_none()
    if not gl:
        raise HTTPException(status_code=404, detail="Grocery list not found")

    existing_result = await db.execute(select(GroceryItem.name).where(GroceryItem.list_id == list_id))
    existing_names = {_normalize_name(name) for name in existing_result.scalars().all() if name}

    suggestions = await _generate_ai_suggestions(db, gl, existing_names)

    added = []
    for s in suggestions:
        normalized_name = _normalize_name(s["name"])
        if normalized_name in existing_names:
            continue
        item = GroceryItem(list_id=list_id, **s)
        db.add(item)
        existing_names.add(normalized_name)
        added.append(s["name"])

    await db.commit()
    return {
        "message": f"Added {len(added)} AI-suggested items",
        "items": added,
    }
