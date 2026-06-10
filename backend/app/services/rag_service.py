from typing import List, Dict, Any, Optional

from app.core.config import settings
from app.core.logging import logger
from app.observability.metrics import TOOL_COUNTER
from app.services.rag_retrieval import (
    build_context_from_candidates,
    chunk_memory_content,
    coerce_text_content,
)


def build_embeddings():
    if settings.openai_api_key:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )

    if settings.google_api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model="text-embedding-004",
            google_api_key=settings.google_api_key,
        )

    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )


def _extract_citation(metadata: Optional[Dict[str, Any]]):
    if not metadata:
        return ""

    citation_parts = []
    filename = metadata.get("filename")
    if filename:
        citation_parts.append(filename)

    page = metadata.get("page")
    if page is not None:
        citation_parts.append(f"page {page}")

    chunk_index = metadata.get("chunk_index")
    if chunk_index is not None:
        citation_parts.append(f"chunk {chunk_index}")

    document_id = metadata.get("document_id")
    if document_id:
        citation_parts.append(f"doc:{document_id}")

    return " | ".join(citation_parts)


class RAGService:
    def _extract_citation(self, metadata: Optional[Dict[str, Any]]):
        return _extract_citation(metadata)

    async def init(self):
        # Canonical storage is the Memory table. The underlying memory service
        # can still initialize its optional vector index lazily.
        from app.memory.memory import memory_service

        await memory_service.init()
        logger.info("rag.initialized")

    async def store_memory(
        self,
        content: Any,
        memory_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ):
        from app.memory.memory import memory_service

        metadata = metadata or {}
        metadata["type"] = memory_type

        TOOL_COUNTER.labels(tool="rag_store").inc()
        chunks = chunk_memory_content(content, memory_type=memory_type, metadata=metadata)
        if not chunks:
            chunks = chunk_memory_content(coerce_text_content(content), memory_type=memory_type, metadata=metadata)

        primary_id = None
        stored_ids = []
        for chunk in chunks or []:
            memory = await memory_service.create_memory(
                content=chunk.content,
                memory_type=memory_type,
                metadata=chunk.metadata,
            )
            if memory and primary_id is None:
                primary_id = memory.id
            if memory:
                stored_ids.append(memory.id)

        if primary_id is None:
            memory = await memory_service.create_memory(
                content=coerce_text_content(content),
                memory_type=memory_type,
                metadata=metadata,
            )
            primary_id = memory.id if memory else None
            if memory:
                stored_ids.append(memory.id)

        if stored_ids and len(stored_ids) > 1:
            logger.info("rag.memory.chunked", memory_type=memory_type, chunks=len(stored_ids))

        return primary_id

    async def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        k: int = 5
    ):
        from app.memory.memory import memory_service

        TOOL_COUNTER.labels(tool="rag_search").inc()
        results = await memory_service.search_memory(
            query=query,
            memory_type=memory_type,
            metadata_filter=metadata_filter,
            k=k,
        )

        return [
            {
                "content": item.get("content"),
                "metadata": item.get("metadata", {}),
                "score": item.get("score", 0.0),
                "bm25_score": item.get("bm25_score", 0.0),
                "rrf_score": item.get("rrf_score", 0.0),
                "cross_encoder_score": item.get("cross_encoder_score", 0.0),
                "citation": self._extract_citation(item.get("metadata", {})),
            }
            for item in results
        ]

    async def build_context(
        self,
        query: str,
        memory_type: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None,
        k: int = 5,
        token_budget: int = settings.rag_context_token_budget,
    ):
        memories = await self.search(
            query,
            memory_type=memory_type,
            metadata_filter=metadata_filter,
            k=max(k * 3, 9),
        )

        if not memories:
            return ""

        context = build_context_from_candidates(memories, token_budget=token_budget, max_items=k)

        return context


rag_service = RAGService()
