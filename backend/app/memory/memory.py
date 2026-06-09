import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from types import SimpleNamespace

from sqlalchemy import select, desc

from app.core.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Memory
from app.services.rag_service import build_embeddings
from app.services.rag_retrieval import (
    candidate_memory_types,
    metadata_matches,
    normalize_text,
    rerank_candidates,
    rewrite_retrieval_query,
    tokenize,
)

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
            self.client = None
            return

        try:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
            )
            await asyncio.to_thread(self._ensure_collection)
        except Exception:
            self.client = None

    def _ensure_collection(self):
        try:
            self.client.get_collection(collection_name=self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance="Cosine"),
            )

    async def _embed_text(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.embeddings.embed_query, text)

    def _build_payload(
        self,
        content: str,
        memory_type: str,
        metadata: Dict[str, Any],
        created_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        metadata = dict(metadata or {})
        flat_payload = {
            "memory_type": memory_type,
            "content": content,
            "metadata": metadata,
            "created_at": created_at,
            "updated_at": None,
            "source": metadata.get("source") or metadata.get("type") or memory_type,
            "type": metadata.get("type") or memory_type,
            "filename": metadata.get("filename"),
            "document_id": metadata.get("document_id"),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "chunk_count": metadata.get("chunk_count"),
            "chunk_type": metadata.get("chunk_type"),
            "category": metadata.get("category") or memory_type,
            "title": metadata.get("title"),
            "tags": metadata.get("tags") or [],
        }
        flat_payload["search_text"] = " ".join(
            str(value)
            for value in [
                content,
                flat_payload["memory_type"],
                flat_payload["source"],
                flat_payload["filename"],
                flat_payload["category"],
                flat_payload["title"],
            ]
            if value
        )
        return flat_payload

    def _serialize_memory(self, memory: Memory, score: Optional[float] = None) -> Dict[str, Any]:
        metadata = memory.memory_metadata or {}
        tags = metadata.get("tags") or []
        importance = metadata.get("importance")

        return {
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type,
            "category": memory.memory_type,
            "tags": tags,
            "importance": importance,
            "metadata": metadata,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
            **({"score": score} if score is not None else {}),
        }

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
                memory_metadata=metadata or {},
            )
            db.add(memory)
            await db.commit()
            await db.refresh(memory)
            return memory

    async def _load_memory_row(self, memory_id: str) -> Optional[Memory]:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Memory).where(Memory.id == memory_id))
            return result.scalar_one_or_none()

    async def _update_memory_row(
        self,
        memory_id: str,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Memory).where(Memory.id == memory_id))
            memory = result.scalar_one_or_none()
            if not memory:
                raise ValueError("Memory not found")

            if content is not None:
                memory.content = content
            if memory_type is not None:
                memory.memory_type = memory_type
            if metadata is not None:
                memory.memory_metadata = metadata

            memory.updated_at = datetime.now(timezone.utc)

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
            try:
                await self.init()
            except Exception:
                self.client = None

        memory = await self._persist_memory_row(
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            embedding_id="",
        )

        if self.client is not None:
            try:
                vector = await self._embed_text(content)
                created_at = (
                    memory.created_at.isoformat()
                    if hasattr(memory.created_at, "isoformat")
                    else memory.created_at
                )
                payload = self._build_payload(
                    content=content,
                    memory_type=memory_type,
                    metadata=metadata or {},
                    created_at=created_at,
                )

                point = (
                    PointStruct(id=memory.id, vector=vector, payload=payload)
                    if PointStruct is not None
                    else SimpleNamespace(id=memory.id, vector=vector, payload=payload)
                )

                await asyncio.to_thread(
                    self.client.upsert,
                    collection_name=self.collection_name,
                    points=[point],
                )
            except Exception:
                pass

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
            try:
                await self.init()
            except Exception:
                self.client = None

        memory = await self._load_memory_row(memory_id)
        if not memory:
            raise ValueError("Memory not found")

        updated_content = content if content is not None else memory.content
        updated_type = memory_type if memory_type is not None else memory.memory_type
        updated_metadata = metadata if metadata is not None else memory.memory_metadata

        updated_memory = await self._update_memory_row(
            memory_id,
            content=updated_content,
            memory_type=updated_type,
            metadata=updated_metadata,
        )

        if self.client is not None and PointStruct is not None:
            try:
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
            except Exception:
                pass

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
        metadata_filter: Optional[Dict[str, Any]] = None,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        if self.client is None:
            try:
                await self.init()
            except Exception:
                self.client = None

        rewritten_query = rewrite_retrieval_query(
            query,
            memory_type=memory_type,
            metadata_filter=metadata_filter,
        )
        allowed_memory_types = candidate_memory_types(query, memory_type=memory_type)
        allowed_memory_types_set = {normalize_text(item) for item in allowed_memory_types if item}
        search_terms = tokenize(rewritten_query)
        search_text = normalize_text(rewritten_query)
        search_limit = max(k * 6, 30)
        candidates: Dict[str, Dict[str, Any]] = {}

        if self.client is not None:
            try:
                query_filter = None

                if (
                    Filter is not None
                    and FieldCondition is not None
                    and MatchValue is not None
                ):
                    query_vector = await self._embed_text(rewritten_query)
                    filter_conditions = []
                    if memory_type:
                        filter_conditions.append(
                            FieldCondition(
                                key="memory_type",
                                match=MatchValue(value=memory_type),
                            )
                        )
                    if metadata_filter:
                        for key, value in metadata_filter.items():
                            if value is None:
                                continue
                            filter_conditions.append(
                                FieldCondition(
                                    key=key,
                                    match=MatchValue(value=value),
                            )
                        )
                    query_filter = Filter(must=filter_conditions) if filter_conditions else None
                else:
                    query_vector = []

                results = await asyncio.to_thread(
                    self.client.search,
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=search_limit,
                    with_payload=True,
                    with_vectors=False,
                )

                for result in results:
                    candidate = self._result_to_candidate(result, rewritten_query, memory_type)
                    if self._accept_candidate(candidate, allowed_memory_types_set, metadata_filter):
                        candidates[self._candidate_key(candidate)] = candidate
            except Exception:
                pass

        memories = []
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(Memory)
                if memory_type:
                    stmt = stmt.where(Memory.memory_type == memory_type)
                stmt = stmt.order_by(desc(Memory.created_at)).limit(max(k * 12, 40))
                result = await db.execute(stmt)
                memories = result.scalars().all()
        except Exception:
            memories = []

        for memory in memories:
            candidate = self._memory_to_candidate(memory, rewritten_query, memory_type)
            if self._accept_candidate(candidate, allowed_memory_types_set, metadata_filter):
                candidates[self._candidate_key(candidate)] = candidate

        ranked = rerank_candidates(
            rewritten_query,
            list(candidates.values()),
            limit=max(k * 2, k),
            metadata_filter=metadata_filter,
            token_budget=0,
        )
        return ranked[:k]

    def _memory_to_candidate(
        self,
        memory: Memory,
        rewritten_query: str,
        memory_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        metadata = memory.memory_metadata or {}
        candidate = self._serialize_memory(memory)
        candidate.update({
            "vector_score": 0.0,
            "lexical_score": self._lexical_score(rewritten_query, memory.content or ""),
            "recency_boost": self._recency_boost(memory.created_at.isoformat() if memory.created_at else None),
            "source": metadata.get("source") or metadata.get("type") or memory.memory_type,
            "filename": metadata.get("filename"),
            "document_id": metadata.get("document_id"),
            "page": metadata.get("page"),
            "chunk_index": metadata.get("chunk_index"),
            "chunk_count": metadata.get("chunk_count"),
            "chunk_type": metadata.get("chunk_type"),
            "title": metadata.get("title"),
        })
        candidate["score"] = self._base_candidate_score(
            candidate,
            normalize_text(rewritten_query),
            tokenize(rewritten_query),
            requested_memory_type=memory_type,
        )
        return candidate

    def _result_to_candidate(
        self,
        result: Any,
        rewritten_query: str,
        memory_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = result.payload or {}
        metadata = payload.get("metadata") or {}
        candidate = {
            "id": str(result.id),
            "content": payload.get("content"),
            "memory_type": payload.get("memory_type"),
            "category": payload.get("memory_type"),
            "tags": payload.get("tags") or metadata.get("tags") or [],
            "importance": metadata.get("importance"),
            "metadata": metadata,
            "source": payload.get("source") or metadata.get("source"),
            "filename": payload.get("filename") or metadata.get("filename"),
            "document_id": payload.get("document_id") or metadata.get("document_id"),
            "page": payload.get("page") or metadata.get("page"),
            "chunk_index": payload.get("chunk_index") or metadata.get("chunk_index"),
            "chunk_count": payload.get("chunk_count") or metadata.get("chunk_count"),
            "chunk_type": payload.get("chunk_type") or metadata.get("chunk_type"),
            "title": payload.get("title") or metadata.get("title"),
            "vector_score": float(result.score or 0.0),
            "lexical_score": self._lexical_score(rewritten_query, payload.get("content") or ""),
            "recency_boost": self._recency_boost(payload.get("created_at")),
            "score": float(result.score or 0.0),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        candidate["rerank_score"] = self._base_candidate_score(
            candidate,
            normalize_text(rewritten_query),
            tokenize(rewritten_query),
            requested_memory_type=memory_type,
        )
        return candidate

    def _accept_candidate(
        self,
        candidate: Dict[str, Any],
        allowed_memory_types_set: set[str],
        metadata_filter: Optional[Dict[str, Any]],
    ) -> bool:
        candidate_type = normalize_text(str(candidate.get("memory_type") or ""))
        return metadata_matches(candidate, metadata_filter) and (
            not allowed_memory_types_set or candidate_type in allowed_memory_types_set
        )

    async def list_memories(
        self,
        memory_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            stmt = select(Memory)
            if memory_type:
                stmt = stmt.where(Memory.memory_type == memory_type)
            stmt = stmt.order_by(desc(Memory.created_at)).limit(limit)
            result = await db.execute(stmt)
            memories = result.scalars().all()

        return [self._serialize_memory(memory) for memory in memories]

    async def delete_memory(self, memory_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Memory).where(Memory.id == memory_id))
            memory = result.scalar_one_or_none()
            if not memory:
                return False

            await db.delete(memory)
            await db.commit()
            return True

    async def categories_summary(self) -> Dict[str, Any]:
        memories = await self.list_memories(limit=10000)
        categories: Dict[str, int] = {}
        for memory in memories:
            category = memory.get("memory_type") or "general"
            categories[category] = categories.get(category, 0) + 1

        return {
            "total": len(memories),
            "categories": categories,
        }

    def _candidate_key(self, candidate: Dict[str, Any]) -> str:
        normalized_content = normalize_text(candidate.get("content") or "")
        if candidate.get("id"):
            return str(candidate["id"])
        return normalized_content

    def _lexical_score(self, query: str, content: str) -> float:
        query_tokens = set(tokenize(query))
        content_tokens = set(tokenize(content))
        if not query_tokens or not content_tokens:
            return 0.0
        overlap = len(query_tokens & content_tokens) / len(query_tokens | content_tokens)
        phrase = 1.0 if normalize_text(query) in normalize_text(content) else 0.0
        return max(overlap, phrase)

    def _base_candidate_score(
        self,
        candidate: Dict[str, Any],
        search_text: str,
        search_terms: List[str],
        requested_memory_type: Optional[str] = None,
    ) -> float:
        content = candidate.get("content") or ""
        if not content:
            return 0.0

        content_lower = normalize_text(content)
        term_hits = sum(1 for term in search_terms if term in content_lower)
        term_score = term_hits / max(1, len(search_terms))
        exact_match = 1.0 if search_text and search_text in content_lower else 0.0
        recency = float(candidate.get("recency_boost", 0.0) or 0.0)
        vector = float(candidate.get("vector_score", 0.0) or 0.0)
        lexical = float(candidate.get("lexical_score", 0.0) or 0.0)
        type_bonus = 1.0 if requested_memory_type and candidate.get("memory_type") == requested_memory_type else 0.0
        return max(0.0, min(1.0, 0.35 * vector + 0.35 * lexical + 0.15 * term_score + 0.10 * recency + 0.05 * exact_match + 0.05 * type_bonus))


memory_service = MemoryService()
