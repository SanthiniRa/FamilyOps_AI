import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy import select

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Memory
from app.services.rag_service import build_embeddings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import (
        Filter,
        FieldCondition,
        MatchValue,
        PointStruct,
        VectorParams,
    )
except ImportError:
    QdrantClient = None
    Filter = None
    FieldCondition = None
    MatchValue = None
    PointStruct = None
    VectorParams = None


class MemoryService:
    def __init__(self):
        self.embeddings = build_embeddings()
        self.client = None
        self.collection_name = settings.qdrant_collection
        self.vector_size = 1536

    async def init(self):
        if QdrantClient is None:
            raise RuntimeError("qdrant-client is required for memory storage")

        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )

        await asyncio.to_thread(self._ensure_collection)

    def _ensure_collection(self):
        try:
            self.client.get_collection(collection_name=self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors=VectorParams(size=self.vector_size, distance="Cosine"),
            )

    async def _embed_text(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.embeddings.embed_query, text)

    async def _persist_memory_row(
        self,
        content: str,
        memory_type: str,
        metadata: Dict[str, Any],
        embedding_id: str,
    ) -> Memory:
        async with AsyncSessionLocal() as db:
            memory = Memory(
                content=content,
                memory_type=memory_type,
                embedding_id=embedding_id,
                metadata=metadata or {},
            )
            db.add(memory)
            await db.commit()
            await db.refresh(memory)
            return memory

    async def _load_memory_row(self, memory_id: str) -> Optional[Memory]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                __import__("sqlalchemy").select(Memory).where(Memory.id == memory_id)
            )
            return result.scalar_one_or_none()

    async def _update_memory_row(
        self,
        memory: Memory,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        if content is not None:
            memory.content = content
        if memory_type is not None:
            memory.memory_type = memory_type
        if metadata is not None:
            memory.metadata = metadata

        memory.updated_at = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as db:
            db.add(memory)
            await db.commit()
            await db.refresh(memory)
            return memory

    async def _set_embedding_id(self, memory_id: str, embedding_id: str) -> Memory:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Memory).where(Memory.id == memory_id))
            memory = result.scalar_one_or_none()
            if not memory:
                raise ValueError("Memory not found")

            memory.embedding_id = embedding_id
            await db.commit()
            await db.refresh(memory)
            return memory

    async def create_memory(
        self,
        content: str,
        memory_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        if self.client is None:
            await self.init()

        memory = await self._persist_memory_row(
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            embedding_id="",
        )

        vector = await self._embed_text(content)
        payload = {
            "memory_type": memory_type,
            "metadata": metadata or {},
            "created_at": memory.created_at.isoformat(),
            "content": content,
        }

        await asyncio.to_thread(
            self.client.upsert,
            collection_name=self.collection_name,
            points=[PointStruct(id=memory.id, vector=vector, payload=payload)],
        )

        memory = await self._set_embedding_id(memory.id, memory.id)
        return memory

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        if self.client is None:
            await self.init()

        memory = await self._load_memory_row(memory_id)
        if not memory:
            raise ValueError("Memory not found")

        updated_content = content if content is not None else memory.content
        updated_type = memory_type if memory_type is not None else memory.memory_type
        updated_metadata = metadata if metadata is not None else memory.metadata

        updated_memory = await self._update_memory_row(
            memory,
            content=updated_content,
            memory_type=updated_type,
            metadata=updated_metadata,
        )

        vector = await self._embed_text(updated_content)
        payload = {
            "memory_type": updated_type,
            "metadata": updated_metadata,
            "created_at": updated_memory.created_at.isoformat(),
            "content": updated_content,
        }

        await asyncio.to_thread(
            self.client.upsert,
            collection_name=self.collection_name,
            points=[PointStruct(id=updated_memory.id, vector=vector, payload=payload)],
        )

        return updated_memory

    def _recency_boost(self, created_at: Optional[str]) -> float:
        if not created_at:
            return 0.0

        try:
            dt = datetime.fromisoformat(created_at)
        except ValueError:
            return 0.0

        age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        return max(0.0, min(1.0, 1.0 - age_days / 365.0))

    def _type_boost(self, memory_type: Optional[str], candidate_type: Optional[str]) -> float:
        if memory_type and candidate_type == memory_type:
            return 1.0
        return 0.0

    async def search_memory(
        self,
        query: str,
        memory_type: Optional[str] = None,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        if self.client is None:
            await self.init()

        query_vector = await self._embed_text(query)
        query_filter = None
        if memory_type and Filter is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="memory_type",
                        match=MatchValue(value=memory_type),
                    )
                ]
            )

        results = await asyncio.to_thread(
            self.client.search,
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=query_filter,
            limit=k,
            with_payload=True,
            with_vectors=False,
        )

        memories = []
        for result in results:
            payload = result.payload or {}
            vector_score = float(result.score or 0.0)
            recency = self._recency_boost(payload.get("created_at"))
            type_boost = self._type_boost(memory_type, payload.get("memory_type"))
            final_score = 0.6 * vector_score + 0.2 * recency + 0.2 * type_boost

            memories.append({
                "id": str(result.id),
                "content": payload.get("content"),
                "memory_type": payload.get("memory_type"),
                "metadata": payload.get("metadata", {}),
                "vector_score": vector_score,
                "recency_boost": recency,
                "type_boost": type_boost,
                "score": final_score,
                "created_at": payload.get("created_at"),
            })

        memories.sort(key=lambda x: x["score"], reverse=True)
        return memories


memory_service = MemoryService()
