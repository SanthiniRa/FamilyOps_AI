from app.core.config import settings
from app.observability.langfuse_client import get_langfuse

langfuse = get_langfuse() if settings.enable_tracing else None


def start_trace(name: str):

    if not langfuse:
        return None

    return langfuse.trace(
        name=name
    )
