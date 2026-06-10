from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Dict, Iterable, List, Optional, Sequence

from .text_utils import (
    best_match_score,
    extract_capitalized_phrases,
    extract_numeric_tokens,
    jaccard_similarity,
    sentence_split,
    sequence_similarity,
    tokenize,
)


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


def estimate_token_count(text: str) -> int:
    tokens = tokenize(text)
    return max(1, len(tokens)) if text and text.strip() else 0


def estimate_cost_units(input_tokens: int, output_tokens: int) -> float:
    return max(0.0, (input_tokens + output_tokens) / 1000.0)


def score_context_precision(retrieved_contexts: Sequence[str], expected_contexts: Sequence[str]) -> float:
    if not retrieved_contexts:
        return 0.0
    relevant = sum(1 for candidate in retrieved_contexts if best_match_score(candidate, expected_contexts) >= 0.45)
    return _clamp(relevant / len(retrieved_contexts))


def score_context_recall(retrieved_contexts: Sequence[str], expected_contexts: Sequence[str]) -> float:
    if not expected_contexts:
        return 1.0
    matched = sum(1 for expected in expected_contexts if best_match_score(expected, retrieved_contexts) >= 0.45)
    return _clamp(matched / len(expected_contexts))


def score_faithfulness(retrieved_contexts: Sequence[str], generated_answer: str) -> float:
    sentences = sentence_split(generated_answer)
    if not sentences:
        return 1.0
    supported = 0
    for sentence in sentences:
        if best_match_score(sentence, retrieved_contexts) >= 0.4:
            supported += 1
            continue
        if extract_numeric_tokens(sentence) and any(token in " ".join(retrieved_contexts) for token in extract_numeric_tokens(sentence)):
            supported += 1
            continue
    return _clamp(supported / len(sentences))


def score_answer_relevance(query: str, generated_answer: str) -> float:
    return _clamp((jaccard_similarity(query, generated_answer) + sequence_similarity(query, generated_answer)) / 2.0)


def score_task_specific(
    category: str,
    query: str,
    generated_answer: str,
    reference_answer: str,
    retrieved_contexts: Sequence[str],
    expected_contexts: Sequence[str],
) -> float:
    category = (category or "").strip().lower()
    base = best_match_score(generated_answer, [reference_answer, *expected_contexts, *retrieved_contexts])

    query_tokens = set(tokenize(query))
    answer_tokens = set(tokenize(generated_answer))
    reference_tokens = set(tokenize(reference_answer))
    context_tokens = set(tokenize(" ".join(expected_contexts + list(retrieved_contexts))))
    overlap_bonus = 0.0

    if category == "email_calendar":
        cue_bonus = 0.0
        if extract_numeric_tokens(generated_answer):
            cue_bonus += 0.12
        if any(word in answer_tokens for word in {"added", "scheduled", "created", "calendar"}):
            cue_bonus += 0.12
        if any(word in query_tokens for word in {"calendar", "schedule", "event", "appointment"}):
            cue_bonus += 0.08
        overlap_bonus = min(0.25, cue_bonus)
    elif category == "meal_planning":
        cue_bonus = 0.0
        if any(word in answer_tokens for word in {"meal", "meals", "dinner", "dinners", "plan", "shopping", "budget"}):
            cue_bonus += 0.10
        if context_tokens & answer_tokens:
            cue_bonus += 0.10
        if reference_tokens & answer_tokens:
            cue_bonus += 0.10
        overlap_bonus = min(0.30, cue_bonus)
    elif category == "memory_lookup":
        cue_bonus = 0.0
        if any(word in answer_tokens for word in {"remember", "saved", "memory", "note"}):
            cue_bonus += 0.10
        if context_tokens & answer_tokens:
            cue_bonus += 0.15
        overlap_bonus = min(0.30, cue_bonus)
    else:
        if context_tokens & answer_tokens:
            overlap_bonus = 0.10

    return _clamp((0.7 * base) + overlap_bonus)


def score_error_handling(error_message: Optional[str], generated_answer: str) -> float:
    if error_message:
        if generated_answer and generated_answer.strip():
            return 0.5
        return 0.0
    return 1.0 if generated_answer and generated_answer.strip() else 0.5


def score_cost_efficiency(estimated_cost_units: float, budget_units: float = 2.0) -> float:
    if budget_units <= 0:
        return 1.0
    return _clamp(1.0 - min(1.0, estimated_cost_units / budget_units))


def score_latency_efficiency(latency_ms: float, budget_ms: float = 4000.0) -> float:
    if budget_ms <= 0:
        return 1.0
    return _clamp(1.0 - min(1.0, latency_ms / budget_ms))


def score_rag_quality(
    query: str,
    retrieved_contexts: Sequence[str],
    expected_contexts: Sequence[str],
    generated_answer: str,
) -> Dict[str, float]:
    context_precision = score_context_precision(retrieved_contexts, expected_contexts)
    context_recall = score_context_recall(retrieved_contexts, expected_contexts)
    faithfulness = score_faithfulness(retrieved_contexts, generated_answer)
    answer_relevance = score_answer_relevance(query, generated_answer)
    rag_quality = mean([context_precision, context_recall, faithfulness, answer_relevance])
    return {
        "context_precision": context_precision,
        "context_recall": context_recall,
        "faithfulness": faithfulness,
        "answer_relevance": answer_relevance,
        "rag_quality": _clamp(rag_quality),
    }


def score_answer_correctness(generated_answer: str, reference_answer: str) -> float:
    return _clamp((jaccard_similarity(generated_answer, reference_answer) + sequence_similarity(generated_answer, reference_answer)) / 2.0)


def score_answer_completeness(generated_answer: str, reference_answer: str) -> float:
    reference_tokens = set(tokenize(reference_answer))
    if not reference_tokens:
        return 1.0
    generated_tokens = set(tokenize(generated_answer))
    return _clamp(len(reference_tokens & generated_tokens) / len(reference_tokens))


def score_answer_coherence(generated_answer: str) -> float:
    sentences = sentence_split(generated_answer)
    if not sentences:
        return 0.0
    penalty = 0.0
    if len(sentences) > 8:
        penalty += 0.15
    if any(sentence.endswith("...") for sentence in sentences):
        penalty += 0.1
    if len(set(tokenize(generated_answer))) < max(6, len(tokenize(generated_answer)) // 2):
        penalty += 0.15
    if generated_answer.count("\n\n") > 4:
        penalty += 0.1
    return _clamp(1.0 - penalty)


def score_answer_usefulness(query: str, generated_answer: str, reference_answer: str, retrieved_contexts: Sequence[str]) -> float:
    relevance = score_answer_relevance(query, generated_answer)
    correctness = score_answer_correctness(generated_answer, reference_answer)
    completeness = score_answer_completeness(generated_answer, reference_answer)
    grounding = score_faithfulness(retrieved_contexts, generated_answer)
    return _clamp(mean([relevance, correctness, completeness, grounding]))


def score_answer_quality(
    query: str,
    generated_answer: str,
    reference_answer: str,
    retrieved_contexts: Sequence[str],
) -> Dict[str, float]:
    correctness = score_answer_correctness(generated_answer, reference_answer)
    completeness = score_answer_completeness(generated_answer, reference_answer)
    coherence = score_answer_coherence(generated_answer)
    usefulness = score_answer_usefulness(query, generated_answer, reference_answer, retrieved_contexts)
    answer_quality = mean([correctness, completeness, coherence, usefulness])
    return {
        "correctness": correctness,
        "completeness": completeness,
        "coherence": coherence,
        "usefulness": usefulness,
        "answer_quality": _clamp(answer_quality),
    }


def score_hallucination(generated_answer: str, retrieved_contexts: Sequence[str]) -> float:
    sentences = sentence_split(generated_answer)
    if not sentences:
        return 0.0
    unsupported = 0
    for sentence in sentences:
        match_score = best_match_score(sentence, retrieved_contexts)
        if match_score < 0.35:
            unsupported += 1
    return _clamp(unsupported / len(sentences))


def score_tool_selection_accuracy(expected_tool: str, predicted_tool: str) -> float:
    return 1.0 if expected_tool == predicted_tool else 0.0


def score_routing_accuracy(expected_agent: str, predicted_agent: str) -> float:
    return 1.0 if expected_agent == predicted_agent else 0.0


def compute_final_score(
    rag_quality: float,
    answer_quality: float,
    hallucination_score: float,
    tool_selection_accuracy: float,
    routing_accuracy: float,
    task_specific_score: float,
    error_handling_score: float,
    cost_efficiency: float,
    latency_efficiency: float,
) -> Dict[str, float]:
    hallucination_penalty = _clamp(1.0 - hallucination_score)
    final_score = (
        0.20 * rag_quality
        + 0.20 * answer_quality
        + 0.15 * hallucination_penalty
        + 0.10 * tool_selection_accuracy
        + 0.10 * routing_accuracy
        + 0.10 * task_specific_score
        + 0.10 * error_handling_score
        + 0.075 * cost_efficiency
        + 0.075 * latency_efficiency
    )
    return {
        "hallucination_penalty": hallucination_penalty,
        "final_score": _clamp(final_score),
    }
