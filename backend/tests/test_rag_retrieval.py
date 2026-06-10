import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.rag_retrieval import (  # noqa: E402
    build_context_from_candidates,
    bm25_score,
    cross_encoder_rerank_candidates,
    metadata_matches,
    rank_candidates_by_bm25,
    reciprocal_rank_fusion,
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


def test_bm25_prefers_exact_keyword_match():
    candidates = [
        {
            "id": "1",
            "content": "Family day out at the aquarium with tickets booked.",
            "memory_type": "event",
            "metadata": {"source": "event"},
        },
        {
            "id": "2",
            "content": "Aquarium opening hours and family-friendly visit tips for the weekend.",
            "memory_type": "event",
            "metadata": {"source": "event"},
        },
    ]

    ranked = rank_candidates_by_bm25("aquarium tickets", candidates)

    assert ranked[0]["id"] == "1"
    assert ranked[0]["bm25_score"] >= ranked[1]["bm25_score"]
    assert bm25_score("aquarium tickets", ranked[0]["content"]) >= bm25_score(
        "aquarium tickets",
        ranked[1]["content"],
    )


def test_reciprocal_rank_fusion_combines_rankings():
    fused = reciprocal_rank_fusion(
        [
            ["a", "b", "c"],
            ["c", "b", "d"],
        ]
    )

    assert fused["b"] > fused["a"]
    assert fused["c"] > fused["a"]
    assert fused["b"] > fused["d"]


def test_cross_encoder_rerank_can_reorder_top_candidates():
    class FakeScorer:
        def predict(self, pairs):
            scores = []
            for _, candidate_text in pairs:
                scores.append(0.95 if "dentist" in candidate_text.lower() else 0.10)
            return scores

    candidates = [
        {"id": "1", "content": "Lunch plans for next week.", "metadata": {}, "score": 0.3},
        {"id": "2", "content": "Dentist appointment reminder for Thursday.", "metadata": {}, "score": 0.3},
        {"id": "3", "content": "Grocery list for the weekend.", "metadata": {}, "score": 0.3},
    ]

    ranked = cross_encoder_rerank_candidates(
        "dentist appointment",
        candidates,
        top_n=2,
        scorer=FakeScorer(),
    )

    assert ranked[0]["id"] == "2"
    assert ranked[0]["cross_encoder_score"] > ranked[1]["cross_encoder_score"]


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
