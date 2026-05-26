from typing import List, Dict, Any, Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from app.core.config import settings
from app.core.logging import logger
import json


def _build_embeddings():
    if settings.google_api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model=settings.google_embedding_model,
            google_api_key=settings.google_api_key,
        )
    elif settings.openai_api_key:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
    return None


class HouseholdRAG:
    def __init__(self):
        self.embeddings = _build_embeddings()
        self.vector_store = None

    async def init(self):
        if not self.embeddings:
            logger.warning("rag.no_ai_key", message="RAG disabled - set GOOGLE_API_KEY or OPENAI_API_KEY")
            return

        try:
            from supabase import create_client
            client = create_client(settings.supabase_url, settings.supabase_service_key)
            self.vector_store = SupabaseVectorStore(
                client=client,
                embedding=self.embeddings,
                table_name="household_memories",
                query_name="match_memories",
            )
            logger.info("rag.initialized")
        except Exception as e:
            logger.warning("rag.init_failed", error=str(e))

    async def store_memory(self, content: str, metadata: Dict[str, Any] = None) -> str:
        if not self.vector_store:
            logger.debug("rag.store_skipped", reason="vector store not initialized")
            return ""

        doc = Document(page_content=content, metadata=metadata or {})
        ids = await self.vector_store.aadd_documents([doc])
        logger.info("rag.memory_stored", id=ids[0] if ids else "unknown")
        return ids[0] if ids else ""

    async def search_memories(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        if not self.vector_store:
            return []

        try:
            docs = await self.vector_store.asimilarity_search_with_relevance_scores(
                query, k=k, filter=filter
            )
            return [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": score,
                }
                for doc, score in docs
            ]
        except Exception as e:
            logger.error("rag.search_error", error=str(e))
            return []

    async def get_context_for_query(self, query: str, k: int = 3) -> str:
        memories = await self.search_memories(query, k=k)
        if not memories:
            return ""

        context_parts = []
        for m in memories:
            context_parts.append(f"[Memory - score: {m['score']:.2f}]\n{m['content']}")

        return "\n\n".join(context_parts)


rag = HouseholdRAG()
