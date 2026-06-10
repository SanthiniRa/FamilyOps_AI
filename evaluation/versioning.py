from __future__ import annotations

from typing import Any, Dict


EVALUATION_VERSION = "2026-06-10.1"
EVALUATION_DATASET_VERSION = "familyops_synthetic_eval_v1"
PROMPT_REGISTRY_VERSION = "2026-06-10.1"

PROMPT_VERSIONS: Dict[str, str] = {
    "orchestrator.system": "1.0.0",
    "orchestrator.intent": "1.0.0",
    "email.action_items": "1.0.0",
    "email.extract": "1.0.0",
    "grocery.suggestions": "1.0.0",
    "meal.recipe_selection": "1.0.0",
}


def prompt_versions() -> Dict[str, str]:
    return dict(PROMPT_VERSIONS)


def build_version_manifest(dataset_name: str, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    prompt_snapshot = prompt_versions()
    return {
        "evaluation_version": EVALUATION_VERSION,
        "dataset_version": dataset_name,
        "prompt_registry_version": PROMPT_REGISTRY_VERSION,
        "prompt_count": len(prompt_snapshot),
        "prompt_versions": prompt_snapshot,
        "meta": dict(meta or {}),
    }
