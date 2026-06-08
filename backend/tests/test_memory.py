import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.memory.memory import MemoryService


class DummyMemory:
    def __init__(self, id, content, memory_type, metadata):
        self.id = id
        self.content = content
        self.memory_type = memory_type
        self.metadata = metadata
        self.embedding_id = ""
        self.created_at = None
        self.updated_at = None


def make_search_point(id, content, memory_type, metadata, score=0.9):
    return type(
        "SearchPoint",
        (),
        {
            "id": id,
            "payload": {
                "content": content,
                "memory_type": memory_type,
                "metadata": metadata,
            },
            "score": score,
        },
    )()


def test_create_memory_upserts_vector():
    service = MemoryService()
    service.client = MagicMock()
    service.client.upsert = MagicMock()

    dummy_memory = DummyMemory("mem-1", "Hello world", "personal", {"topic": "test"})
    dummy_memory.created_at = "2026-01-01T00:00:00Z"
    dummy_memory.updated_at = "2026-01-01T00:00:00Z"

    service._persist_memory_row = AsyncMock(return_value=dummy_memory)
    service._embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    service._set_embedding_id = AsyncMock(return_value=dummy_memory)

    result = asyncio.run(
        service.create_memory(
            content="Hello world",
            memory_type="personal",
            metadata={"topic": "test"},
        )
    )

    service.client.upsert.assert_called_once()
    call_args = service.client.upsert.call_args[1]
    assert call_args["collection_name"] == service.collection_name
    points = call_args["points"]
    assert len(points) == 1
    assert points[0].id == "mem-1"
    assert points[0].vector == [0.1, 0.2, 0.3]
    assert result is dummy_memory


def test_update_memory_missing_raises_value_error():
    service = MemoryService()
    service._load_memory_row = AsyncMock(return_value=None)

    try:
        asyncio.run(
            service.update_memory(
                memory_id="missing",
                content="Updated",
                memory_type=None,
                metadata=None,
            )
        )
    except ValueError as exc:
        assert str(exc) == "Memory not found"
    else:
        raise AssertionError("Expected ValueError for missing memory")


def test_search_memory_returns_results_with_type_filter():
    service = MemoryService()
    service.client = MagicMock()
    service.client.search = MagicMock(
        return_value=[
            make_search_point(
                id="mem-1",
                content="Hello world",
                memory_type="personal",
                metadata={"topic": "test"},
                score=0.95,
            )
        ]
    )

    results = asyncio.run(
        service.search_memory(query="Hello", memory_type="personal", k=1)
    )

    assert len(results) == 1
    assert results[0]["id"] == "mem-1"
    assert results[0]["content"] == "Hello world"
    assert results[0]["memory_type"] == "personal"
    assert results[0]["score"] == 0.95
