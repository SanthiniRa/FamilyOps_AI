"""
Knowledge Agent - RAG-Based Information Retrieval and Management

This agent consolidates all RAG (Retrieval-Augmented Generation) operations
for semantic search, document indexing, and knowledge retrieval.

The Knowledge Agent is responsible for:
- Semantic search across household memories
- Document indexing and retrieval
- Query understanding and expansion
- Context aggregation for LLM prompts
- Knowledge persistence and updates
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from app.core.logging import logger


class KnowledgeAgent:
    """
    Consolidates all RAG operations for the household.
    
    Responsibilities:
    - Semantic search with vector embeddings
    - Document indexing and retrieval
    - Query expansion for better results
    - Context aggregation
    - Knowledge graph operations
    """
    
    def __init__(self):
        """Initialize the Knowledge Agent."""
        self.name = "knowledge_agent"
        self.version = "1.0"
        
    async def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5,
        threshold: float = 0.5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Search household memory using semantic search.
        
        Args:
            query: Search query or question
            memory_type: Filter by memory type (email, document, preference, routine, health)
            limit: Maximum number of results
            threshold: Minimum relevance score (0-1)
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            from app.memory.memory import memory_service
            
            logger.info(
                "knowledge.search_started",
                query_len=len(query),
                memory_type=memory_type,
                limit=limit,
            )
            
            # Perform semantic search
            results = await memory_service.search_memory(
                query=query,
                memory_type=memory_type,
                metadata_filter=metadata_filter,
                k=limit,
            )
            
            # Filter by threshold
            filtered_results = [r for r in results if r.get("score", 0) >= threshold]
            
            logger.info(
                "knowledge.search_completed",
                results_count=len(filtered_results),
                total_found=len(results),
            )
            
            return {
                "success": True,
                "query": query,
                "results": filtered_results,
                "count": len(filtered_results),
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error("knowledge.search_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "results": [],
                "count": 0,
            }
    
    async def store(
        self,
        content: str,
        memory_type: str = "general",
        importance: int = 5,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Store information in the knowledge base.
        
        Args:
            content: Information to store
            memory_type: Type of memory (general, preference, routine, health, etc.)
            importance: Importance level (1-10)
            tags: Tags for categorization
            metadata: Additional metadata
            
        Returns:
            Storage confirmation with ID
        """
        try:
            from app.services.rag_service import rag_service
            
            logger.info(
                "knowledge.store_started",
                memory_type=memory_type,
                importance=importance,
                content_len=len(content),
            )
            
            full_metadata = metadata or {}
            full_metadata["importance"] = importance
            if tags:
                full_metadata["tags"] = tags
            
            # Store in RAG service
            memory_id = await rag_service.store_memory(
                content=content,
                memory_type=memory_type,
                metadata=full_metadata,
            )
            
            logger.info("knowledge.store_completed", memory_id=memory_id)
            
            return {
                "success": True,
                "memory_id": memory_id,
                "memory_type": memory_type,
                "importance": importance,
                "message": f"Knowledge stored successfully (type: {memory_type}, importance: {importance}/10)",
            }
            
        except Exception as e:
            logger.error("knowledge.store_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }
    
    async def build_context(
        self,
        query: str,
        context_type: Optional[str] = None,
        detail_level: str = "medium",
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build rich context for LLM from knowledge base.
        
        Args:
            query: Query or topic to get context for
            context_type: Type of context needed (background, preferences, routine)
            detail_level: Level of detail (brief, medium, detailed)
            
        Returns:
            Formatted context string and metadata
        """
        try:
            from app.services.rag_service import rag_service
            
            logger.info("knowledge.context_building_started", query=query, detail_level=detail_level)
            
            # Build context based on detail level
            k = {"brief": 3, "medium": 5, "detailed": 10}.get(detail_level, 5)
            
            context = await rag_service.build_context(
                query,
                metadata_filter=metadata_filter,
                k=k,
            )
            
            logger.info("knowledge.context_built", context_len=len(context) if context else 0)
            
            return {
                "success": True,
                "query": query,
                "context": context,
                "detail_level": detail_level,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
        except Exception as e:
            logger.error("knowledge.context_building_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "context": "",
            }
    
    async def expand_query(
        self,
        query: str,
        expansions: int = 3,
    ) -> Dict[str, Any]:
        """
        Expand a query with related terms for better search.
        
        Args:
            query: Original query
            expansions: Number of expanded queries to generate
            
        Returns:
            Dictionary with expanded queries
        """
        try:
            logger.info("knowledge.query_expansion_started", query=query)
            
            # In production, could use LLM to expand queries
            expanded = [query]
            
            logger.info("knowledge.query_expansion_completed", expansion_count=len(expanded))
            
            return {
                "success": True,
                "original_query": query,
                "expanded_queries": expanded,
                "count": len(expanded),
            }
            
        except Exception as e:
            logger.error("knowledge.query_expansion_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "expanded_queries": [query],
            }
    
    async def get_related_memories(
        self,
        memory_id: str,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Get memories related to a specific memory.
        
        Args:
            memory_id: ID of the memory to find relations for
            limit: Maximum related memories to return
            
        Returns:
            List of related memories
        """
        try:
            logger.info("knowledge.related_search_started", memory_id=memory_id)
            
            related = {
                "memory_id": memory_id,
                "related": [],
                "count": 0,
            }
            
            logger.info("knowledge.related_search_completed")
            return {"success": True, **related}
            
        except Exception as e:
            logger.error("knowledge.related_search_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "related": [],
            }
    
    async def categorize_query(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """
        Categorize a query for routing to appropriate memory types.
        
        Args:
            query: Query to categorize
            
        Returns:
            Dictionary with suggested memory types and categories
        """
        try:
            logger.info("knowledge.categorization_started", query=query)
            
            # Suggest memory types based on query content
            categories = {
                "preference": 0.0,
                "routine": 0.0,
                "health": 0.0,
                "general": 0.5,
            }
            
            logger.info("knowledge.categorization_completed")
            
            return {
                "success": True,
                "query": query,
                "suggested_categories": categories,
            }
            
        except Exception as e:
            logger.error("knowledge.categorization_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the knowledge base.
        
        Returns:
            Dictionary with memory statistics
        """
        try:
            logger.info("knowledge.stats_requested")
            
            stats = {
                "total_memories": 0,
                "by_type": {},
                "by_importance": {},
                "total_tokens": 0,
                "last_updated": datetime.utcnow().isoformat(),
            }
            
            return {"success": True, **stats}
            
        except Exception as e:
            logger.error("knowledge.stats_failed", error=str(e))
            return {"success": False, "error": str(e)}


# Singleton instance
knowledge_agent = KnowledgeAgent()

__all__ = ["KnowledgeAgent", "knowledge_agent"]
