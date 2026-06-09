import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.rag_retrieval import (  # noqa: E402
    build_context_from_candidates,
    metadata_matches,
    rerank_candidates,
    rewrite_retrieval_query,
    split_semantic_chunks,
)


def test_rewrite_retrieval_query_adds_domain_terms():
    rewritten = rewrite_retrieval_query(
        "What memory did we save about the holiday travel airport?",
    )
    assert "memory" in rewritten
    assert "airport" in rewritten
    assert "travel" in rewritten


def test_split_semantic_chunks_preserves_boundaries():
    text = "First sentence about dinner.\n\nSecond paragraph about dessert."
    chunks = split_semantic_chunks(text, max_words=8, overlap=0)
    assert len(chunks) >= 2
    assert "dinner" in chunks[0].lower()
    assert "dessert" in chunks[-1].lower()


def test_metadata_matches_checks_flat_and_nested_fields():
    candidate = {
        "source": "email",
        "metadata": {"document_id": "doc-1", "filename": "invoice.pdf"},
    }
    assert metadata_matches(candidate, {"source": "email"})
    assert metadata_matches(candidate, {"document_id": "doc-1"})
    assert not metadata_matches(candidate, {"source": "document"})


def test_rerank_candidates_prefers_relevant_candidate():
    candidates = [
        {
            "id": "1",
            "content": "Dentist appointment on Friday at 3 PM.",
            "memory_type": "email",
            "metadata": {"source": "email"},
            "vector_score": 0.9,
            "lexical_score": 0.8,
            "recency_boost": 0.2,
            "score": 0.6,
        },
        {
            "id": "2",
            "content": "Dinner ideas for the week.",
            "memory_type": "meal_plan",
            "metadata": {"source": "meal"},
            "vector_score": 0.2,
            "lexical_score": 0.1,
            "recency_boost": 0.1,
            "score": 0.2,
        },
    ]

    ranked = rerank_candidates(
        "Add the dentist appointment to my calendar",
        candidates,
        limit=1,
        metadata_filter={"source": "email"},
        token_budget=200,
    )

    assert ranked[0]["id"] == "1"
    assert ranked[0]["score"] >= ranked[0]["rerank_score"] - 1e-6


def test_build_context_from_candidates_limits_budget():
    context = build_context_from_candidates(
        [
            {"content": "First relevant chunk", "metadata": {"filename": "a.pdf"}, "memory_type": "document"},
            {"content": "Second relevant chunk", "metadata": {"filename": "b.pdf"}, "memory_type": "document"},
        ],
        token_budget=8,
        max_items=2,
    )
    assert "First relevant chunk" in context
    assert "Second relevant chunk" not in context or context.count("\n") <= 1
