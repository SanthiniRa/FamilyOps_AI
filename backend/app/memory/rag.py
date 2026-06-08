"""Thin compatibility wrapper for the canonical RAG service.

This module delegates to `app.services.rag_service.rag_service` so the rest
of the codebase can continue to import `app.memory.rag.rag` and call the
old methods while we keep a single implementation in `services/rag_service.py`.
"""

from typing import List, Dict, Any, Optional
from app.services.rag_service import rag_service


class RagWrapper:
    async def init(self):
        return await rag_service.init()

    async def store_memory(self, content: str, metadata: Dict[str, Any] = None) -> str:
        # keep backwards-compatible call: previous API accepted (content, metadata)
        memory_type = None
        if metadata and isinstance(metadata, dict):
            memory_type = metadata.get("type")
        return await rag_service.store_memory(content=content, memory_type=memory_type or "general", metadata=metadata)

    async def search_memories(self, query: str, k: int = 5, filter: Optional[Dict] = None) -> List[Dict[str, Any]]:
        # delegate to service.search which returns list of {content, metadata, score}
        return await rag_service.search(query=query, memory_type=(filter.get("type") if filter else None), k=k)

    async def get_context_for_query(self, query: str, k: int = 3) -> str:
        return await rag_service.build_context(query)


rag = RagWrapper()
