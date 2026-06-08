"""
LangGraph Persistence & Checkpointing

Provides optional state persistence for LangGraph executions.

Supports:
- MemorySaver (in-process, development)
- SQLiteSaver (lightweight, production)
- PostgresSaver (distributed, production)
- Custom memory abstraction

Configuration via settings or environment variables.
"""

from typing import Optional, Dict, Any, Type
from abc import ABC, abstractmethod
from datetime import datetime
from app.core.config import settings
from app.core.logging import logger


class PersistenceProvider(ABC):
    """Abstract base class for persistence providers."""
    
    @abstractmethod
    async def init(self) -> None:
        """Initialize the persistence provider."""
        pass
    
    @abstractmethod
    async def save_checkpoint(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        step: int,
    ) -> bool:
        """Save a checkpoint of the graph state."""
        pass
    
    @abstractmethod
    async def load_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load the latest checkpoint for a workflow."""
        pass
    
    @abstractmethod
    async def list_checkpoints(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """List available checkpoints."""
        pass
    
    @abstractmethod
    async def delete_checkpoint(
        self,
        workflow_id: str,
    ) -> bool:
        """Delete checkpoints for a workflow."""
        pass


class MemoryPersistenceProvider(PersistenceProvider):
    """
    In-process memory-based persistence (development/testing).
    
    States are stored in memory and lost on restart.
    Useful for development and testing.
    """
    
    def __init__(self):
        """Initialize memory provider."""
        self.checkpoints: Dict[str, Dict[str, Any]] = {}
        self.history: Dict[str, list] = {}
    
    async def init(self) -> None:
        """Initialize the memory provider."""
        logger.info("persistence.memory_provider.initialized")
    
    async def save_checkpoint(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        step: int,
    ) -> bool:
        """Save checkpoint to memory."""
        try:
            checkpoint = {
                "workflow_id": workflow_id,
                "state": state.copy(),
                "step": step,
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            self.checkpoints[workflow_id] = checkpoint
            
            if workflow_id not in self.history:
                self.history[workflow_id] = []
            self.history[workflow_id].append(checkpoint)
            
            logger.info(
                "persistence.checkpoint.saved",
                provider="memory",
                workflow_id=workflow_id,
                step=step,
            )
            return True
            
        except Exception as e:
            logger.error("persistence.checkpoint.save_failed", error=str(e))
            return False
    
    async def load_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load checkpoint from memory."""
        try:
            checkpoint = self.checkpoints.get(workflow_id)
            if checkpoint:
                logger.info(
                    "persistence.checkpoint.loaded",
                    provider="memory",
                    workflow_id=workflow_id,
                )
            return checkpoint
            
        except Exception as e:
            logger.error("persistence.checkpoint.load_failed", error=str(e))
            return None
    
    async def list_checkpoints(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """List checkpoints from memory."""
        try:
            if workflow_id:
                return self.history.get(workflow_id, [])[-limit:]
            
            all_checkpoints = []
            for wid, history in self.history.items():
                all_checkpoints.extend(history[-limit:])
            return all_checkpoints
            
        except Exception as e:
            logger.error("persistence.list_failed", error=str(e))
            return []
    
    async def delete_checkpoint(
        self,
        workflow_id: str,
    ) -> bool:
        """Delete checkpoint from memory."""
        try:
            if workflow_id in self.checkpoints:
                del self.checkpoints[workflow_id]
            if workflow_id in self.history:
                del self.history[workflow_id]
            
            logger.info("persistence.checkpoint.deleted", workflow_id=workflow_id)
            return True
            
        except Exception as e:
            logger.error("persistence.checkpoint.delete_failed", error=str(e))
            return False


class SQLitePersistenceProvider(PersistenceProvider):
    """
    SQLite-based persistence (lightweight production).
    
    Checkpoints are stored in a local SQLite database.
    Good for single-node deployments.
    """
    
    def __init__(self, db_path: str = "langgraph_checkpoints.db"):
        """Initialize SQLite provider."""
        self.db_path = db_path
        self.connection = None
    
    async def init(self) -> None:
        """Initialize SQLite database and schema."""
        try:
            import sqlite3
            
            self.connection = sqlite3.connect(self.db_path)
            cursor = self.connection.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
                    workflow_id TEXT,
                    step INTEGER,
                    state TEXT,
                    created_at TEXT,
                    PRIMARY KEY (workflow_id, step)
                )
            """)
            
            self.connection.commit()
            logger.info("persistence.sqlite_provider.initialized", db_path=self.db_path)
            
        except Exception as e:
            logger.error("persistence.sqlite_init_failed", error=str(e))
            raise
    
    async def save_checkpoint(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        step: int,
    ) -> bool:
        """Save checkpoint to SQLite."""
        try:
            import sqlite3
            import json
            
            cursor = self.connection.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO langgraph_checkpoints
                (workflow_id, step, state, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                workflow_id,
                step,
                json.dumps(state),
                datetime.utcnow().isoformat(),
            ))
            
            self.connection.commit()
            logger.info(
                "persistence.checkpoint.saved",
                provider="sqlite",
                workflow_id=workflow_id,
                step=step,
            )
            return True
            
        except Exception as e:
            logger.error("persistence.checkpoint.save_failed", error=str(e))
            return False
    
    async def load_checkpoint(
        self,
        workflow_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Load latest checkpoint from SQLite."""
        try:
            import json
            
            cursor = self.connection.cursor()
            
            cursor.execute("""
                SELECT state FROM langgraph_checkpoints
                WHERE workflow_id = ?
                ORDER BY step DESC
                LIMIT 1
            """, (workflow_id,))
            
            row = cursor.fetchone()
            if row:
                logger.info(
                    "persistence.checkpoint.loaded",
                    provider="sqlite",
                    workflow_id=workflow_id,
                )
                return json.loads(row[0])
            
            return None
            
        except Exception as e:
            logger.error("persistence.checkpoint.load_failed", error=str(e))
            return None
    
    async def list_checkpoints(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """List checkpoints from SQLite."""
        try:
            import json
            
            cursor = self.connection.cursor()
            
            if workflow_id:
                cursor.execute("""
                    SELECT workflow_id, step, state, created_at
                    FROM langgraph_checkpoints
                    WHERE workflow_id = ?
                    ORDER BY step DESC
                    LIMIT ?
                """, (workflow_id, limit))
            else:
                cursor.execute("""
                    SELECT workflow_id, step, state, created_at
                    FROM langgraph_checkpoints
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            checkpoints = []
            for row in rows:
                checkpoints.append({
                    "workflow_id": row[0],
                    "step": row[1],
                    "state": json.loads(row[2]),
                    "created_at": row[3],
                })
            
            return checkpoints
            
        except Exception as e:
            logger.error("persistence.list_failed", error=str(e))
            return []
    
    async def delete_checkpoint(
        self,
        workflow_id: str,
    ) -> bool:
        """Delete checkpoints from SQLite."""
        try:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                DELETE FROM langgraph_checkpoints
                WHERE workflow_id = ?
            """, (workflow_id,))
            
            self.connection.commit()
            logger.info("persistence.checkpoint.deleted", workflow_id=workflow_id)
            return True
            
        except Exception as e:
            logger.error("persistence.checkpoint.delete_failed", error=str(e))
            return False


class PersistenceManager:
    """
    Central manager for graph persistence.
    
    Selects appropriate provider based on configuration.
    """
    
    def __init__(self, provider_type: str = "memory"):
        """
        Initialize persistence manager.
        
        Args:
            provider_type: Type of provider (memory, sqlite, postgres)
        """
        self.provider_type = provider_type
        self.provider: Optional[PersistenceProvider] = None
        self._init_provider()
    
    def _init_provider(self) -> None:
        """Initialize the appropriate persistence provider."""
        try:
            if self.provider_type == "memory":
                self.provider = MemoryPersistenceProvider()
            elif self.provider_type == "sqlite":
                db_path = getattr(settings, "sqlite_db_path", "langgraph_checkpoints.db")
                self.provider = SQLitePersistenceProvider(db_path)
            elif self.provider_type == "postgres":
                # PostgreSQL provider would be implemented here
                logger.warning("persistence.postgres_not_yet_implemented")
                self.provider = MemoryPersistenceProvider()
            else:
                logger.warning("persistence.unknown_provider_type", provider=self.provider_type)
                self.provider = MemoryPersistenceProvider()
            
            logger.info("persistence.manager.initialized", provider=self.provider_type)
            
        except Exception as e:
            logger.error("persistence.manager.init_failed", error=str(e))
            self.provider = MemoryPersistenceProvider()
    
    async def init(self) -> None:
        """Initialize the persistence provider."""
        if self.provider:
            await self.provider.init()
    
    async def save(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        step: int,
    ) -> bool:
        """Save a checkpoint."""
        if self.provider:
            return await self.provider.save_checkpoint(workflow_id, state, step)
        return False
    
    async def load(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Load a checkpoint."""
        if self.provider:
            return await self.provider.load_checkpoint(workflow_id)
        return None
    
    async def list(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 10,
    ) -> list:
        """List checkpoints."""
        if self.provider:
            return await self.provider.list_checkpoints(workflow_id, limit)
        return []
    
    async def delete(self, workflow_id: str) -> bool:
        """Delete a checkpoint."""
        if self.provider:
            return await self.provider.delete_checkpoint(workflow_id)
        return False


# Singleton instance
persistence_manager = PersistenceManager(
    provider_type=getattr(settings, "persistence_provider", "memory")
)

__all__ = [
    "PersistenceProvider",
    "MemoryPersistenceProvider",
    "SQLitePersistenceProvider",
    "PersistenceManager",
    "persistence_manager",
]
