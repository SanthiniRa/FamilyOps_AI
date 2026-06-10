import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.api.routes.dashboard import version  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.prompt_versioning import (  # noqa: E402
    PROMPT_REGISTRY_VERSION,
    prompt_metadata,
    prompt_versions,
)


def test_prompt_version_registry_exposes_known_prompts():
    versions = prompt_versions()

    assert versions["orchestrator.intent"] == "1.0.0"
    assert versions["email.extract"] == "1.0.0"
    assert len(versions) >= 6


def test_prompt_metadata_includes_registry_version():
    metadata = prompt_metadata("meal.recipe_selection")

    assert metadata["prompt_key"] == "meal.recipe_selection"
    assert metadata["prompt_version"] == "1.0.0"
    assert metadata["prompt_registry_version"] == PROMPT_REGISTRY_VERSION


def test_dashboard_version_endpoint_includes_prompt_snapshot(monkeypatch):
    async def _run():
        monkeypatch.setattr(settings, "app_version", "9.9.9")

        payload = await version()

        assert payload["app_version"] == "9.9.9"
        assert payload["prompt_registry_version"] == PROMPT_REGISTRY_VERSION
        assert payload["prompt_versions"]["orchestrator.system"] == "1.0.0"
        assert payload["prompt_count"] == len(prompt_versions())

    asyncio.run(_run())
