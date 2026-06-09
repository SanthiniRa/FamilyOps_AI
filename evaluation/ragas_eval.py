from __future__ import annotations

from typing import Dict, Sequence

from evaluation.metrics.scoring import score_rag_quality


def evaluate_ragas_case(query: str, retrieved_contexts: Sequence[str], generated_answer: str, expected_contexts: Sequence[str]) -> Dict[str, float]:
    """Return RAGAS-style retrieval scores with a deterministic fallback.

    The function is intentionally dependency-safe: if the native `ragas`
    package is available in the runtime, the code path can be extended to use
    it, but the default implementation always produces CI-safe numeric scores.
    """
    return score_rag_quality(query, retrieved_contexts, expected_contexts, generated_answer)

