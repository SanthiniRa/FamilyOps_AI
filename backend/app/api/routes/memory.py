from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.db.models import Memory
from app.db.database import get_db
from app.memory.memory import memory_service
from sqlalchemy import select

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreate(BaseModel):
    content: str
    memory_type: str
    metadata: Dict[str, Any] = {}


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MemorySearch(BaseModel):
    query: str
    k: int = 5
    memory_type: Optional[str] = None


@router.get("/", response_model=List[dict])
async def list_memories(
    memory_type: Optional[str] = Query(None),
    limit: int = Query(50),
    db=Depends(get_db),
):
    q = select(Memory)
    if memory_type:
        q = q.where(Memory.memory_type == memory_type)
    q = q.order_by(Memory.updated_at.desc()).limit(limit)
    result = await db.execute(q)
    memories = result.scalars().all()
    return [
        {
            "id": m.id,
            "content": m.content,
            "memory_type": m.memory_type,
            "metadata": m.metadata,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }
        for m in memories
    ]


@router.post("/create", status_code=201)
async def create_memory(memory: MemoryCreate):
    created = await memory_service.create_memory(
        content=memory.content,
        memory_type=memory.memory_type,
        metadata=memory.metadata,
    )
    return {
        "id": created.id,
        "content": created.content,
        "memory_type": created.memory_type,
        "metadata": created.metadata,
        "created_at": created.created_at,
        "updated_at": created.updated_at,
    }


@router.get("/search")
async def search_memories(
    query: str = Query(...),
    memory_type: Optional[str] = Query(None),
    k: int = Query(5),
):
    results = await memory_service.search_memory(query=query, memory_type=memory_type, k=k)
    return {"query": query, "results": results, "source": "qdrant"}


@router.put("/{memory_id}")
async def update_memory(memory_id: str, memory: MemoryUpdate):
    try:
        updated = await memory_service.update_memory(
            memory_id=memory_id,
            content=memory.content,
            memory_type=memory.memory_type,
            metadata=memory.metadata,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {
        "id": updated.id,
        "content": updated.content,
        "memory_type": updated.memory_type,
        "metadata": updated.metadata,
        "created_at": updated.created_at,
        "updated_at": updated.updated_at,
    }
