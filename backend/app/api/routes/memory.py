from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.db.models import Memory
from app.db.database import get_db
from app.memory.memory import memory_service
from sqlalchemy import select

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryCreate(BaseModel):
    content: str
    memory_type: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    importance: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    memory_type: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class MemorySearch(BaseModel):
    query: str
    k: int = 5
    memory_type: Optional[str] = None
    source: Optional[str] = None
    document_id: Optional[str] = None
    category: Optional[str] = None
    filename: Optional[str] = None


@router.get("", response_model=List[dict])
@router.get("/", response_model=List[dict])
async def list_memories(
    memory_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(50),
):
    memories = await memory_service.list_memories(
        memory_type=memory_type or category,
        limit=limit,
    )
    return [
        {
            "id": m["id"],
            "content": m["content"],
            "memory_type": m["memory_type"],
            "category": m["category"],
            "tags": m.get("tags", []),
            "importance": m.get("importance"),
            "metadata": m["metadata"],
            "created_at": m["created_at"],
            "updated_at": m["updated_at"],
        }
        for m in memories
    ]


@router.post("", status_code=201)
@router.post("/", status_code=201)
@router.post("/create", status_code=201)
async def create_memory(memory: MemoryCreate):
    memory_type = memory.memory_type or memory.category or "general"
    metadata = dict(memory.metadata or {})
    metadata.setdefault("tags", memory.tags)
    if memory.importance is not None:
        metadata["importance"] = memory.importance

    created = await memory_service.create_memory(
        content=memory.content,
        memory_type=memory_type,
        metadata=metadata,
    )
    return {
        "id": created.id,
        "content": created.content,
        "memory_type": created.memory_type,
        "category": created.memory_type,
        "tags": created.memory_metadata.get("tags", []),
        "importance": created.memory_metadata.get("importance"),
        "metadata": created.memory_metadata,
        "created_at": created.created_at,
        "updated_at": created.updated_at,
    }


async def _search_memory_payload(memory: MemorySearch):
    metadata_filter = {
        key: value
        for key, value in {
            "source": memory.source,
            "document_id": memory.document_id,
            "category": memory.category,
            "filename": memory.filename,
        }.items()
        if value
    }
    results = await memory_service.search_memory(
        query=memory.query,
        memory_type=memory.memory_type,
        metadata_filter=metadata_filter or None,
        k=memory.k,
    )
    return {"query": memory.query, "results": results, "source": "memory"}


@router.post("/search")
async def search_memories(memory: MemorySearch):
    return await _search_memory_payload(memory)


@router.get("/search")
@router.get("/search/")
async def search_memories_legacy(
    query: str = Query(...),
    memory_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    k: int = Query(5),
):
    return await _search_memory_payload(
        MemorySearch(
            query=query,
            memory_type=memory_type or category,
            source=source,
            document_id=document_id,
            filename=filename,
            category=category,
            k=k,
        )
    )


@router.get("/categories/summary")
@router.get("/categories/summary/")
async def categories_summary():
    return await memory_service.categories_summary()


@router.delete("/{memory_id}", status_code=204)
@router.delete("/{memory_id}/", status_code=204)
async def delete_memory(memory_id: str):
    deleted = await memory_service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return None


@router.put("/{memory_id}")
@router.put("/{memory_id}/")
async def update_memory(memory_id: str, memory: MemoryUpdate):
    try:
        metadata: Optional[Dict[str, Any]] = None
        if memory.metadata is not None or memory.tags is not None or memory.importance is not None:
            metadata = dict(memory.metadata or {})
            if memory.tags is not None:
                metadata["tags"] = memory.tags
            if memory.importance is not None:
                metadata["importance"] = memory.importance

        updated = await memory_service.update_memory(
            memory_id=memory_id,
            content=memory.content,
            memory_type=memory.memory_type,
            metadata=metadata,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Memory not found")

    return {
        "id": updated.id,
        "content": updated.content,
        "memory_type": updated.memory_type,
        "category": updated.memory_type,
        "tags": updated.memory_metadata.get("tags", []),
        "importance": updated.memory_metadata.get("importance"),
        "metadata": updated.memory_metadata,
        "created_at": updated.created_at,
        "updated_at": updated.updated_at,
    }
