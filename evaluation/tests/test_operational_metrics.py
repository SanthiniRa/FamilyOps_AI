from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.metrics.scoring import (  # noqa: E402
    compute_final_score,
    estimate_cost_units,
    estimate_token_count,
    score_cost_efficiency,
    score_error_handling,
    score_latency_efficiency,
    score_task_specific,
)


def test_task_specific_scoring_prefers_matching_calendar_answer():
    matching = score_task_specific(
        category="email_calendar",
        query="Add the dentist appointment to my calendar for Friday at 3 PM.",
        generated_answer="I added the dentist appointment for Friday at 3 PM to the calendar.",
        reference_answer="I added the dentist appointment for Friday at 3 PM to the calendar.",
        retrieved_contexts=["Dentist appointment on Friday at 3 PM."],
        expected_contexts=["Dentist appointment on Friday at 3 PM."],
    )
    weak = score_task_specific(
        category="email_calendar",
        query="Add the dentist appointment to my calendar for Friday at 3 PM.",
        generated_answer="I found some household notes.",
        reference_answer="I added the dentist appointment for Friday at 3 PM to the calendar.",
        retrieved_contexts=["Dentist appointment on Friday at 3 PM."],
        expected_contexts=["Dentist appointment on Friday at 3 PM."],
    )

    assert matching > weak


def test_error_cost_and_latency_helpers_are_bounded():
    tokens = estimate_token_count("one two three four")
    cost_units = estimate_cost_units(tokens, tokens)
    fast = score_latency_efficiency(250.0)
    slow = score_latency_efficiency(5000.0)
    clean = score_error_handling(None, "All good.")
    failed = score_error_handling("boom", "I could not complete this task.")
    cost_score = score_cost_efficiency(cost_units)

    assert tokens == 4
    assert cost_units > 0
    assert 0.0 <= cost_score <= 1.0
    assert fast > slow
    assert clean > failed


def test_final_score_uses_operational_metrics():
    good = compute_final_score(
        rag_quality=0.9,
        answer_quality=0.9,
        hallucination_score=0.1,
        tool_selection_accuracy=1.0,
        routing_accuracy=1.0,
        task_specific_score=0.9,
        error_handling_score=1.0,
        cost_efficiency=1.0,
        latency_efficiency=1.0,
    )
    bad = compute_final_score(
        rag_quality=0.9,
        answer_quality=0.9,
        hallucination_score=0.1,
        tool_selection_accuracy=1.0,
        routing_accuracy=1.0,
        task_specific_score=0.1,
        error_handling_score=0.0,
        cost_efficiency=0.0,
        latency_efficiency=0.0,
    )

    assert good["final_score"] > bad["final_score"]
