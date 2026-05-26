from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from app.db.database import get_db
from app.db.models import HouseholdMemory
from app.events.bus import event_bus

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreate(BaseModel):
    content: str
    category: Optional[str] = None
    tags: List[str] = []
    source: Optional[str] = "manual"
    importance: float = 0.5
    metadata: dict = {}


class MemorySearch(BaseModel):
    query: str
    k: int = 5
    category: Optional[str] = None


@router.get("/", response_model=List[dict])
async def list_memories(
    category: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db)
):
    q = select(HouseholdMemory)
    if category:
        q = q.where(HouseholdMemory.category == category)
    q = q.order_by(HouseholdMemory.importance.desc(), HouseholdMemory.created_at.desc()).limit(limit)
    result = await db.execute(q)
    memories = result.scalars().all()
    return [
        {
            "id": m.id, "content": m.content, "category": m.category,
            "tags": m.tags, "source": m.source, "importance": m.importance,
            "created_at": m.created_at, "expires_at": m.expires_at,
        }
        for m in memories
    ]


@router.post("/", status_code=201)
async def store_memory(memory: MemoryCreate, db: AsyncSession = Depends(get_db)):
    db_memory = HouseholdMemory(**memory.model_dump())
    db.add(db_memory)
    await db.flush()
    await event_bus.publish("memory.stored", {
        "memory_id": db_memory.id, "category": db_memory.category,
        "source": db_memory.source,
    })
    return {
        "id": db_memory.id, "content": db_memory.content,
        "category": db_memory.category, "created_at": db_memory.created_at,
    }


@router.post("/search")
async def search_memories(search: MemorySearch, db: AsyncSession = Depends(get_db)):
    from app.memory.rag import rag
    results = await rag.search_memories(search.query, k=search.k)
    if not results:
        q = select(HouseholdMemory)
        if search.category:
            q = q.where(HouseholdMemory.category == search.category)
        q = q.order_by(HouseholdMemory.importance.desc()).limit(search.k)
        db_result = await db.execute(q)
        memories = db_result.scalars().all()
        return {
            "query": search.query,
            "results": [
                {"id": m.id, "content": m.content, "category": m.category,
                 "importance": m.importance, "score": m.importance}
                for m in memories
            ],
            "source": "database",
        }
    return {"query": search.query, "results": results, "source": "vector"}


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HouseholdMemory).where(HouseholdMemory.id == memory_id))
    memory = result.scalar_one_or_none()
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    await db.delete(memory)


@router.get("/categories/summary")
async def memory_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HouseholdMemory))
    memories = result.scalars().all()
    categories = {}
    for m in memories:
        cat = m.category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    return {"categories": categories, "total": len(memories)}
