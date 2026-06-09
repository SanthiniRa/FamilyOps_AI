from contextlib import contextmanager
from typing import Optional, Dict, Any
import time
import uuid
from app.core.logging import logger
from app.core.config import settings
from app.observability.langfuse_client import get_langfuse


class Tracer:
    """
    Lightweight unified tracer:
    - Langfuse (if enabled)
    - fallback logging
    """

    def __init__(self):
        self.langfuse = get_langfuse() if settings.enable_tracing else None

    def trace(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        return TraceSpan(self, name, metadata or {})


class TraceSpan:
    def __init__(self, tracer: Tracer, name: str, metadata: Dict[str, Any]):
        self.tracer = tracer
        self.name = name
        self.metadata = metadata
        self.start_time = None
        self.id = str(uuid.uuid4())

    def __enter__(self):
        self.start_time = time.time()

        logger.info(
            "trace.start",
            trace_id=self.id,
            name=self.name,
            **self.metadata,
        )

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time

        logger.info(
            "trace.end",
            trace_id=self.id,
            name=self.name,
            duration=duration,
            error=str(exc_val) if exc_val else None,
        )


# ============================================================
# GLOBAL TRACER (THIS FIXES YOUR IMPORT ERROR)
# ============================================================

tracer = Tracer()
