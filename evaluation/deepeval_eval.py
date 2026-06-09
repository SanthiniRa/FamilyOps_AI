from __future__ import annotations

from typing import Dict, Sequence

from evaluation.metrics.scoring import (
    score_answer_quality,
    score_hallucination,
    score_routing_accuracy,
    score_tool_selection_accuracy,
)


def evaluate_answer_quality(query: str, generated_answer: str, reference_answer: str, retrieved_contexts: Sequence[str]) -> Dict[str, float]:
    return score_answer_quality(query, generated_answer, reference_answer, retrieved_contexts)


def evaluate_hallucination(generated_answer: str, retrieved_contexts: Sequence[str]) -> float:
    return score_hallucination(generated_answer, retrieved_contexts)


def evaluate_tool_selection(expected_tool: str, predicted_tool: str) -> float:
    return score_tool_selection_accuracy(expected_tool, predicted_tool)


def evaluate_routing(expected_agent: str, predicted_agent: str) -> float:
    return score_routing_accuracy(expected_agent, predicted_agent)

