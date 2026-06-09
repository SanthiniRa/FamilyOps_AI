from __future__ import annotations

import os
from typing import List, Optional

from app.core.config import settings


def openai_chat_model_candidates(primary: Optional[str] = None) -> List[str]:
    configured = primary or settings.openai_model

    fallback_env = os.getenv("OPENAI_MODEL_FALLBACKS") or os.getenv("OPENAI_CHAT_MODEL_FALLBACKS") or ""
    explicit_fallbacks = [
        model.strip()
        for model in fallback_env.split(",")
        if model.strip()
    ]

    candidates = [configured, *explicit_fallbacks]
    seen = set()
    ordered: List[str] = []
    for model in candidates:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)

    if not ordered and configured:
        ordered.append(configured)
    return ordered


def openai_embedding_model_candidates(primary: Optional[str] = None) -> List[str]:
    candidates = [
        primary or settings.openai_embedding_model,
        "text-embedding-3-small",
        "text-embedding-3-large",
    ]
    seen = set()
    ordered: List[str] = []
    for model in candidates:
        if model and model not in seen:
            seen.add(model)
            ordered.append(model)
    return ordered


def is_openai_model_not_found_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "model_not_found" in text
        or "does not have access to model" in text
        or "model `gpt" in text and "not found" in text
        or "model" in text and "not found" in text
    )
