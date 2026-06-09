from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from langfuse import Langfuse
except Exception:  # pragma: no cover - optional dependency/runtime guard
    Langfuse = None

from app.core.config import settings
from app.core.logging import logger


langfuse: Optional["Langfuse"] = None


def _create_langfuse():
    if not Langfuse:
        return None

    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


langfuse = _create_langfuse()


def get_langfuse():
    return langfuse


def _normalize_usage_payload(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None

    if hasattr(usage, "model_dump"):
        payload = usage.model_dump()
    elif isinstance(usage, dict):
        payload = dict(usage)
    else:
        return None

    if not payload:
        return None

    if {"prompt_tokens", "completion_tokens", "total_tokens"} & payload.keys():
        return {
            "input": payload.get("prompt_tokens") or payload.get("input_tokens"),
            "output": payload.get("completion_tokens") or payload.get("output_tokens"),
            "total": payload.get("total_tokens"),
            "unit": "TOKENS",
        }

    if {"input_tokens", "output_tokens", "total_tokens"} & payload.keys():
        return {
            "input": payload.get("input_tokens"),
            "output": payload.get("output_tokens"),
            "total": payload.get("total_tokens"),
            "unit": "TOKENS",
        }

    if {"input", "output", "total"} & payload.keys():
        return payload

    return payload


def start_ai_trace(
    name: str,
    *,
    input: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    if not langfuse:
        return None

    try:
        return langfuse.trace(
            name=name,
            input=input,
            metadata=metadata,
            user_id=user_id,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.exception(
            "observability.langfuse.trace_failed",
            name=name,
            error=str(exc),
        )
        return None


def end_ai_generation(
    trace,
    *,
    name: str,
    model: str,
    input: Any = None,
    output: Any = None,
    usage: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: str = "DEFAULT",
    status_message: Optional[str] = None,
    model_parameters: Optional[Dict[str, Any]] = None,
):
    if not trace:
        return None

    try:
        generation = trace.generation(
            name=name,
            model=model,
            input=input,
            metadata=metadata,
            level=level,
            status_message=status_message,
            model_parameters=model_parameters,
        )
        return generation.end(
            name=name,
            model=model,
            input=input,
            output=output,
            usage=_normalize_usage_payload(usage),
            metadata=metadata,
            level=level,
            status_message=status_message,
            model_parameters=model_parameters,
            end_time=datetime.now(timezone.utc),
        )
    except Exception as exc:
        logger.exception(
            "observability.langfuse.generation_failed",
            name=name,
            model=model,
            error=str(exc),
        )
        return None


def flush_langfuse() -> None:
    if not langfuse:
        return

    try:
        langfuse.flush()
    except Exception as exc:
        logger.exception("observability.langfuse.flush_failed", error=str(exc))
