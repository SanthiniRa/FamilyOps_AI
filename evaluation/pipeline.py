from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from statistics import mean
from typing import Dict, List, Sequence

from evaluation.deepeval_eval import (
    evaluate_answer_quality,
    evaluate_hallucination,
    evaluate_routing,
    evaluate_tool_selection,
)
from evaluation.metrics.schemas import EvaluationCase, EvaluationCaseResult, EvaluationReport
from evaluation.metrics.scoring import compute_final_score
from evaluation.ragas_eval import evaluate_ragas_case
from evaluation.runners.system_adapter import SyntheticSystemAdapter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "dataset" / "evaluation_dataset.json"
DEFAULT_RESULTS = ROOT / "evaluation" / "results.json"
PASS_THRESHOLD = 0.80


async def _run_case(case: EvaluationCase, adapter: SyntheticSystemAdapter, evidence_mode: str) -> EvaluationCaseResult:
    predicted_intent = await adapter.predict_intent(case.input_query)
    predicted_tool = adapter.select_tool(predicted_intent)
    predicted_agent = adapter.select_agent(predicted_intent)
    if evidence_mode == "live":
        retrieved_contexts = adapter.retrieve_contexts(case.input_query, limit=3)
        generated_answer = adapter.generate_answer(case.to_dict(), retrieved_contexts)
    else:
        retrieved_contexts = case.expected_retrieved_context
        generated_answer = case.reference_answer

    rag_metrics = evaluate_ragas_case(
        query=case.input_query,
        retrieved_contexts=retrieved_contexts,
        generated_answer=generated_answer,
        expected_contexts=case.expected_retrieved_context,
    )
    answer_metrics = evaluate_answer_quality(
        query=case.input_query,
        generated_answer=generated_answer,
        reference_answer=case.reference_answer,
        retrieved_contexts=retrieved_contexts,
    )
    hallucination_score = evaluate_hallucination(generated_answer, retrieved_contexts)
    tool_selection_accuracy = evaluate_tool_selection(case.expected_tool, predicted_tool)
    routing_accuracy = evaluate_routing(case.expected_agent, predicted_agent)
    score_bundle = compute_final_score(
        rag_quality=rag_metrics["rag_quality"],
        answer_quality=answer_metrics["answer_quality"],
        hallucination_score=hallucination_score,
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
    )

    return EvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        input_query=case.input_query,
        expected_intent_label=case.expected_intent_label,
        predicted_intent_label=predicted_intent,
        expected_tool=case.expected_tool,
        predicted_tool=predicted_tool,
        expected_agent=case.expected_agent,
        predicted_agent=predicted_agent,
        retrieved_contexts=retrieved_contexts,
        reference_answer=case.reference_answer,
        generated_answer=generated_answer,
        rag_metrics=rag_metrics,
        answer_metrics=answer_metrics,
        hallucination_score=hallucination_score,
        hallucination_penalty=score_bundle["hallucination_penalty"],
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
        final_score=score_bundle["final_score"],
    )


async def run_pipeline(
    dataset_path: Path = DEFAULT_DATASET,
    results_path: Path = DEFAULT_RESULTS,
    pass_threshold: float = PASS_THRESHOLD,
    evidence_mode: str = "baseline",
) -> EvaluationReport:
    dataset_payload = json.loads(dataset_path.read_text())
    cases = [EvaluationCase.from_dict(item) for item in dataset_payload["cases"]]
    adapter = SyntheticSystemAdapter([case.to_dict() for case in cases])

    results = [await _run_case(case, adapter, evidence_mode) for case in cases]

    rag_quality = mean(result.rag_metrics["rag_quality"] for result in results)
    context_precision = mean(result.rag_metrics["context_precision"] for result in results)
    context_recall = mean(result.rag_metrics["context_recall"] for result in results)
    faithfulness = mean(result.rag_metrics["faithfulness"] for result in results)
    answer_relevance = mean(result.rag_metrics["answer_relevance"] for result in results)
    answer_quality = mean(result.answer_metrics["answer_quality"] for result in results)
    hallucination_penalty = mean(result.hallucination_penalty for result in results)
    tool_selection_accuracy = mean(result.tool_selection_accuracy for result in results)
    routing_accuracy = mean(result.routing_accuracy for result in results)
    final_score = mean(result.final_score for result in results)
    passed = final_score >= pass_threshold

    report = EvaluationReport(
        dataset_name=str(dataset_payload.get("dataset_name", "evaluation_dataset")),
        total_cases=len(results),
        pass_threshold=pass_threshold,
        final_score=final_score,
        rag_quality=rag_quality,
        rag_metrics={
            "context_precision": context_precision,
            "context_recall": context_recall,
            "faithfulness": faithfulness,
            "answer_relevance": answer_relevance,
        },
        answer_quality=answer_quality,
        hallucination_penalty=hallucination_penalty,
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
        passed=passed,
        cases=results,
        meta=dataset_payload.get("meta", {}),
    )

    results_path.write_text(json.dumps(report.to_dict(), indent=2))
    _print_summary(report)
    return report


def _print_summary(report: EvaluationReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print("\n=== FamilyOps Evaluation Summary ===")
    print(f"Dataset: {report.dataset_name}")
    print(f"Cases: {report.total_cases}")
    print(f"Final score: {report.final_score:.3f} (threshold {report.pass_threshold:.2f})")
    print(f"RAG quality: {report.rag_quality:.3f}")
    print(f"Context precision: {report.rag_metrics['context_precision']:.3f}")
    print(f"Context recall: {report.rag_metrics['context_recall']:.3f}")
    print(f"Faithfulness: {report.rag_metrics['faithfulness']:.3f}")
    print(f"Answer relevancy: {report.rag_metrics['answer_relevance']:.3f}")
    print(f"Answer quality: {report.answer_quality:.3f}")
    print(f"Hallucination penalty: {report.hallucination_penalty:.3f}")
    print(f"Tool selection accuracy: {report.tool_selection_accuracy:.3f}")
    print(f"Routing accuracy: {report.routing_accuracy:.3f}")
    print(f"Status: {status}")
    print("===================================\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FamilyOps evaluation pipeline")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--threshold", type=float, default=PASS_THRESHOLD)
    parser.add_argument("--mode", choices=["baseline", "live"], default=os.getenv("EVAL_MODE", "baseline"))
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = asyncio.run(run_pipeline(args.dataset, args.results, args.threshold, args.mode))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
