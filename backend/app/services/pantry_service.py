"""
Pantry Management Service

Manages household pantry inventory including:
- Item tracking
- Quantity management
- Expiry date handling
- Reorder suggestions
- Usage tracking
- Integration with meal planning
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PantryItem
from app.core.logging import logger


class PantryService:
    """Manages pantry inventory and operations."""
    
    async def add_item(
        self,
        db: AsyncSession,
        name: str,
        quantity: float,
        unit: str = "unit",
        category: Optional[str] = None,
        expiry_date: Optional[datetime] = None,
        location: Optional[str] = None,
        min_quantity: float = 0,
        price_per_unit: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> PantryItem:
        """Add an item to the pantry."""
        try:
            item = PantryItem(
                name=name.lower(),
                quantity=quantity,
                unit=unit,
                category=category or "misc",
                expiry_date=expiry_date,
                location=location,
                min_quantity=min_quantity,
                price_per_unit=price_per_unit,
                notes=notes,
            )
            db.add(item)
            await db.flush()
            
            logger.info(
                "pantry.item_added",
                item_id=item.id,
                name=name,
                quantity=quantity,
            )
            return item
            
        except Exception as e:
            logger.error("pantry.add_item_failed", error=str(e))
            raise
    
    async def update_item(
        self,
        db: AsyncSession,
        item_id: str,
        quantity: Optional[float] = None,
        expiry_date: Optional[datetime] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional[PantryItem]:
        """Update a pantry item."""
        try:
            result = await db.execute(
                select(PantryItem).where(PantryItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return None
            
            if quantity is not None:
                item.quantity = quantity
            if expiry_date is not None:
                item.expiry_date = expiry_date
            if location is not None:
                item.location = location
            if notes is not None:
                item.notes = notes
            
            item.updated_at = datetime.now(timezone.utc)
            await db.flush()
            
            logger.info("pantry.item_updated", item_id=item_id)
            return item
            
        except Exception as e:
            logger.error("pantry.update_item_failed", error=str(e))
            raise
    
    async def use_item(
        self,
        db: AsyncSession,
        item_id: str,
        quantity: float,
    ) -> Optional[PantryItem]:
        """Decrement item quantity when used."""
        try:
            result = await db.execute(
                select(PantryItem).where(PantryItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return None
            
            item.quantity -= quantity
            item.updated_at = datetime.now(timezone.utc)
            await db.flush()
            
            logger.info(
                "pantry.item_used",
                item_id=item_id,
                quantity_used=quantity,
                quantity_remaining=item.quantity,
            )
            return item
            
        except Exception as e:
            logger.error("pantry.use_item_failed", error=str(e))
            raise
    
    async def remove_item(
        self,
        db: AsyncSession,
        item_id: str,
    ) -> bool:
        """Remove an item from the pantry."""
        try:
            result = await db.execute(
                select(PantryItem).where(PantryItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            
            if not item:
                return False
            
            await db.delete(item)
            logger.info("pantry.item_removed", item_id=item_id)
            return True
            
        except Exception as e:
            logger.error("pantry.remove_item_failed", error=str(e))
            raise
    
    async def get_items(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
    ) -> List[PantryItem]:
        """Get all pantry items, optionally filtered by category."""
        try:
            query = select(PantryItem)
            
            if category:
                query = query.where(PantryItem.category == category)
            
            result = await db.execute(query.order_by(PantryItem.category, PantryItem.name))
            return result.scalars().all()
            
        except Exception as e:
            logger.error("pantry.get_items_failed", error=str(e))
            raise
    
    async def get_item(
        self,
        db: AsyncSession,
        item_id: str,
    ) -> Optional[PantryItem]:
        """Get a specific pantry item."""
        try:
            result = await db.execute(
                select(PantryItem).where(PantryItem.id == item_id)
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error("pantry.get_item_failed", error=str(e))
            raise
    
    async def find_item_by_name(
        self,
        db: AsyncSession,
        name: str,
    ) -> Optional[PantryItem]:
        """Find a pantry item by name (case-insensitive)."""
        try:
            result = await db.execute(
                select(PantryItem).where(
                    PantryItem.name == name.lower()
                )
            )
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error("pantry.find_item_failed", error=str(e))
            raise
    
    async def get_low_stock_items(
        self,
        db: AsyncSession,
    ) -> List[PantryItem]:
        """Get items that are below minimum quantity threshold."""
        try:
            result = await db.execute(
                select(PantryItem).where(
                    PantryItem.quantity < PantryItem.min_quantity
                ).order_by(PantryItem.quantity.asc())
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error("pantry.get_low_stock_failed", error=str(e))
            raise
    
    async def get_expired_items(
        self,
        db: AsyncSession,
    ) -> List[PantryItem]:
        """Get items that have expired or are expiring soon."""
        try:
            now = datetime.now(timezone.utc)
            soon = now + timedelta(days=7)  # Expiring within 7 days
            
            result = await db.execute(
                select(PantryItem).where(
                    and_(
                        PantryItem.expiry_date.isnot(None),
                        PantryItem.expiry_date <= soon
                    )
                ).order_by(PantryItem.expiry_date.asc())
            )
            return result.scalars().all()
            
        except Exception as e:
            logger.error("pantry.get_expired_items_failed", error=str(e))
            raise
    
    def get_pantry_dict(
        self,
        items: List[PantryItem],
    ) -> List[Dict[str, Any]]:
        """Convert pantry items to dict format for meal planner."""
        return [
            {
                "name": item.name,
                "quantity": item.quantity,
                "unit": item.unit,
                "category": item.category,
            }
            for item in items
        ]
    
    async def get_pantry_summary(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """Get summary statistics about pantry."""
        try:
            all_items = await self.get_items(db)
            low_stock = await self.get_low_stock_items(db)
            expired = await self.get_expired_items(db)
            
            total_value = sum(
                (item.price_per_unit or 0) * item.quantity
                for item in all_items
            )
            
            return {
                "total_items": len(all_items),
                "total_value": round(total_value, 2),
                "low_stock_count": len(low_stock),
                "expired_soon_count": len(expired),
                "by_category": self._count_by_category(all_items),
            }
            
        except Exception as e:
            logger.error("pantry.summary_failed", error=str(e))
            raise
    
    def _count_by_category(self, items: List[PantryItem]) -> Dict[str, int]:
        """Count items by category."""
        counts = {}
        for item in items:
            category = item.category or "uncategorized"
            counts[category] = counts.get(category, 0) + 1
        return counts


# Singleton instance
pantry_service = PantryService()

__all__ = ["PantryService", "pantry_service"]
