from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


PROMPT_REGISTRY_VERSION = "2026-06-10.1"


@dataclass(frozen=True)
class PromptVersion:
    key: str
    version: str


PROMPT_VERSIONS: Dict[str, str] = {
    "orchestrator.system": "1.0.0",
    "orchestrator.intent": "1.0.0",
    "email.action_items": "1.0.0",
    "email.extract": "1.0.0",
    "grocery.suggestions": "1.0.0",
    "meal.recipe_selection": "1.0.0",
}


def get_prompt_version(key: str) -> str:
    return PROMPT_VERSIONS[key]


def prompt_metadata(key: str) -> Dict[str, str]:
    return {
        "prompt_key": key,
        "prompt_version": get_prompt_version(key),
        "prompt_registry_version": PROMPT_REGISTRY_VERSION,
    }


def prompt_versions() -> Dict[str, str]:
    return dict(PROMPT_VERSIONS)
