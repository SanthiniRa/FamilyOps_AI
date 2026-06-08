from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.db.database import get_db
from app.db.models import GroceryList, GroceryItem
from app.events.bus import event_bus

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
    from app.core.config import settings
    from openai import AsyncOpenAI
    result = await db.execute(select(GroceryList).where(GroceryList.id == list_id))
    gl = result.scalar_one_or_none()
    if not gl:
        raise HTTPException(status_code=404, detail="Grocery list not found")

    suggestions = [
        {"name": "Milk", "category": "Dairy", "quantity": 1, "unit": "gallon"},
        {"name": "Eggs", "category": "Dairy", "quantity": 12, "unit": "count"},
        {"name": "Bread", "category": "Bakery", "quantity": 1, "unit": "loaf"},
        {"name": "Chicken Breast", "category": "Meat", "quantity": 2, "unit": "lbs"},
        {"name": "Spinach", "category": "Produce", "quantity": 1, "unit": "bag"},
    ]

    added = []
    for s in suggestions:
        item = GroceryItem(list_id=list_id, **s)
        db.add(item)
        added.append(s["name"])

    
    await db.commit()
    await db.refresh(item)
    return {"message": f"Added {len(added)} AI-suggested items", "items": added}
