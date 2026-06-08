"""
Pantry API Routes

Handles pantry inventory management including:
- Adding/removing items
- Quantity tracking
- Expiry date management
- Low stock alerts
- Pantry summaries
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.db.database import get_db
from app.services.pantry_service import pantry_service
from app.events.bus import event_bus
from app.core.logging import logger

router = APIRouter(prefix="/pantry", tags=["pantry"])


# ============================================================
# SCHEMAS
# ============================================================

class PantryItemCreate(BaseModel):
    name: str
    quantity: float
    unit: str = "unit"
    category: Optional[str] = None
    expiry_date: Optional[datetime] = None
    location: Optional[str] = None
    min_quantity: float = 0
    price_per_unit: Optional[float] = None
    notes: Optional[str] = None


class PantryItemUpdate(BaseModel):
    quantity: Optional[float] = None
    expiry_date: Optional[datetime] = None
    location: Optional[str] = None
    notes: Optional[str] = None


class PantryItemUse(BaseModel):
    quantity: float = Field(gt=0)


class PantryItemResponse(BaseModel):
    id: str
    name: str
    quantity: float
    unit: str
    category: str
    expiry_date: Optional[datetime]
    location: Optional[str]
    min_quantity: float
    price_per_unit: Optional[float]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================
# ENDPOINTS
# ============================================================

@router.get("", response_model=List[PantryItemResponse])
async def list_pantry_items(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all pantry items, optionally filtered by category."""
    try:
        items = await pantry_service.get_items(db, category=category)
        return items
    except Exception as e:
        logger.error("pantry.list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", status_code=201, response_model=PantryItemResponse)
async def create_pantry_item(
    data: PantryItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add a new item to the pantry."""
    try:
        item = await pantry_service.add_item(
            db,
            name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            category=data.category,
            expiry_date=data.expiry_date,
            location=data.location,
            min_quantity=data.min_quantity,
            price_per_unit=data.price_per_unit,
            notes=data.notes,
        )
        await db.commit()
        await db.refresh(item)
        
        await event_bus.publish("pantry.item.added", {
            "item_id": item.id,
            "name": item.name,
            "quantity": item.quantity,
        })
        
        return item
    except Exception as e:
        logger.error("pantry.create_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{item_id}", response_model=PantryItemResponse)
async def get_pantry_item(
    item_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a specific pantry item."""
    try:
        item = await pantry_service.get_item(db, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pantry.get_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{item_id}", response_model=PantryItemResponse)
async def update_pantry_item(
    item_id: str,
    data: PantryItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a pantry item."""
    try:
        item = await pantry_service.update_item(
            db,
            item_id,
            quantity=data.quantity,
            expiry_date=data.expiry_date,
            location=data.location,
            notes=data.notes,
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        await db.commit()
        await db.refresh(item)
        
        await event_bus.publish("pantry.item.updated", {
            "item_id": item_id,
            "quantity": data.quantity,
        })
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pantry.update_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{item_id}/use", response_model=PantryItemResponse)
async def use_pantry_item(
    item_id: str,
    data: PantryItemUse,
    db: AsyncSession = Depends(get_db)
):
    """Decrement item quantity when used (e.g., in meal preparation)."""
    try:
        item = await pantry_service.use_item(db, item_id, data.quantity)
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        await db.commit()
        await db.refresh(item)
        
        # Alert if low on stock
        if item.quantity < item.min_quantity:
            await event_bus.publish("pantry.item.low_stock", {
                "item_id": item_id,
                "name": item.name,
                "quantity": item.quantity,
                "min_quantity": item.min_quantity,
            })
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pantry.use_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{item_id}", status_code=204)
async def delete_pantry_item(
    item_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Remove an item from the pantry."""
    try:
        success = await pantry_service.remove_item(db, item_id)
        if not success:
            raise HTTPException(status_code=404, detail="Item not found")
        
        await db.commit()
        
        await event_bus.publish("pantry.item.removed", {
            "item_id": item_id,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pantry.delete_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=dict)
async def get_pantry_summary(db: AsyncSession = Depends(get_db)):
    """Get pantry summary statistics."""
    try:
        summary = await pantry_service.get_pantry_summary(db)
        return summary
    except Exception as e:
        logger.error("pantry.summary_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/low-stock", response_model=List[PantryItemResponse])
async def get_low_stock_items(db: AsyncSession = Depends(get_db)):
    """Get items that are below minimum quantity."""
    try:
        items = await pantry_service.get_low_stock_items(db)
        return items
    except Exception as e:
        logger.error("pantry.low_stock_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/expiring", response_model=List[PantryItemResponse])
async def get_expiring_items(db: AsyncSession = Depends(get_db)):
    """Get items that are expired or expiring soon (within 7 days)."""
    try:
        items = await pantry_service.get_expired_items(db)
        return items
    except Exception as e:
        logger.error("pantry.expiring_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["router"]
