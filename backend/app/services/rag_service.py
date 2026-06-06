from typing import List, Dict, Any, Optional
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_core.documents import Document
from app.core.config import settings
from app.core.logging import logger


def build_embeddings():
    if settings.google_api_key:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(
            model="text-embedding-004",
            google_api_key=settings.google_api_key,
        )

    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )


class RAGService:
    def __init__(self):
        self.embeddings = build_embeddings()
        self.vector_store = None

    async def init(self):
        from supabase import create_client

        client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )

        self.vector_store = SupabaseVectorStore(
            client=client,
            embedding=self.embeddings,
            table_name="household_memories",
            query_name="match_memories",
        )

        logger.info("rag.initialized")

    # ======================================================
    # STORE MEMORY (WITH TYPE TAGGING)
    # ======================================================
    async def store_memory(
        self,
        content: str,
        memory_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ):
        metadata = metadata or {}
        metadata["type"] = memory_type

        doc = Document(
            page_content=content,
            metadata=metadata
        )

        ids = await self.vector_store.aadd_documents([doc])
        return ids[0] if ids else None

    # ======================================================
    # HYBRID SEARCH (IMPORTANT IMPROVEMENT)
    # ======================================================
    async def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        k: int = 5
    ):
        if not self.vector_store:
            return []

        filter_dict = {}
        if memory_type:
            filter_dict = {"type": memory_type}

        results = await self.vector_store.asimilarity_search_with_relevance_scores(
            query,
            k=k,
            filter=filter_dict if filter_dict else None
        )

        return [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score,
            }
            for doc, score in results
        ]

    # ======================================================
    # CONTEXT BUILDER (VERY IMPORTANT FOR LLM QUALITY)
    # ======================================================
    async def build_context(self, query: str):
        memories = await self.search(query, k=5)

        if not memories:
            return ""

        context = "\n\n".join(
            f"[score={m['score']:.2f} | type={m['metadata'].get('type')}]\n{m['content']}"
            for m in memories
        )

        return context


rag_service = RAGService()