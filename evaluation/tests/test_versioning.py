from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.metrics.schemas import EvaluationCaseResult, EvaluationReport  # noqa: E402
from evaluation.versioning import (  # noqa: E402
    build_version_manifest,
    EVALUATION_VERSION,
    PROMPT_REGISTRY_VERSION,
    prompt_versions,
)


def test_version_manifest_is_stable():
    versions = prompt_versions()

    assert versions["orchestrator.system"] == "1.0.0"
    assert versions["grocery.suggestions"] == "1.0.0"
    assert PROMPT_REGISTRY_VERSION == "2026-06-10.1"
    assert EVALUATION_VERSION == "2026-06-10.1"


def test_evaluation_report_serializes_versions():
    versions = prompt_versions()

    report = EvaluationReport(
        dataset_name="familyops_synthetic_eval_v1",
        evaluation_version=EVALUATION_VERSION,
        total_cases=1,
        pass_threshold=0.8,
        final_score=1.0,
        rag_quality=1.0,
        rag_metrics={"context_precision": 1.0, "context_recall": 1.0, "faithfulness": 1.0, "answer_relevance": 1.0},
        answer_quality=1.0,
        task_specific_score=1.0,
        error_handling_score=1.0,
        hallucination_penalty=0.0,
        tool_selection_accuracy=1.0,
        routing_accuracy=1.0,
        estimated_tokens=10.0,
        estimated_cost_units=0.01,
        latency_ms=1.0,
        retrieval_latency_ms=1.0,
        generation_latency_ms=1.0,
        passed=True,
        cases=[
            EvaluationCaseResult(
                case_id="case-1",
                category="general",
                input_query="Hello",
                expected_intent_label="general",
                predicted_intent_label="general",
                expected_tool="general_tool",
                predicted_tool="general_tool",
                expected_agent="general_agent",
                predicted_agent="general_agent",
                retrieved_contexts=[],
                reference_answer="Hello",
                generated_answer="Hello",
                rag_metrics={},
                answer_metrics={},
                task_specific_score=1.0,
                error_handling_score=1.0,
                hallucination_score=0.0,
                hallucination_penalty=0.0,
                tool_selection_accuracy=1.0,
                routing_accuracy=1.0,
                estimated_tokens=10,
                estimated_cost_units=0.01,
                latency_ms=1.0,
                retrieval_latency_ms=1.0,
                generation_latency_ms=1.0,
                error_message=None,
                final_score=1.0,
            )
        ],
        prompt_versions=versions,
        meta={"prompt_registry_version": PROMPT_REGISTRY_VERSION},
    )

    payload = report.to_dict()

    assert payload["evaluation_version"] == EVALUATION_VERSION
    assert payload["prompt_versions"]["orchestrator.system"] == "1.0.0"
    assert payload["meta"]["prompt_registry_version"] == PROMPT_REGISTRY_VERSION


def test_version_manifest_includes_dataset_and_prompt_snapshot():
    manifest = build_version_manifest(
        dataset_name="familyops_synthetic_eval_v1",
        meta={"branch": "main"},
    )

    assert manifest["evaluation_version"] == EVALUATION_VERSION
    assert manifest["dataset_version"] == "familyops_synthetic_eval_v1"
    assert manifest["prompt_registry_version"] == PROMPT_REGISTRY_VERSION
    assert manifest["prompt_versions"]["email.extract"] == "1.0.0"
    assert manifest["meta"]["branch"] == "main"
