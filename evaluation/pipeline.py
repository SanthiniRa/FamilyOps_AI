from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
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
from evaluation.metrics.scoring import (
    compute_final_score,
    estimate_cost_units,
    estimate_token_count,
    score_cost_efficiency,
    score_error_handling,
    score_latency_efficiency,
    score_task_specific,
)
from evaluation.versioning import (
    build_version_manifest,
    EVALUATION_DATASET_VERSION,
    EVALUATION_VERSION,
    PROMPT_REGISTRY_VERSION,
    prompt_versions,
)
from evaluation.ragas_eval import evaluate_ragas_case
from evaluation.runners.system_adapter import SyntheticSystemAdapter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "dataset" / "evaluation_dataset.json"
DEFAULT_RESULTS = ROOT / "evaluation" / "results.json"
PASS_THRESHOLD = 0.80


async def _run_case(case: EvaluationCase, adapter: SyntheticSystemAdapter, evidence_mode: str) -> EvaluationCaseResult:
    started = time.perf_counter()
    retrieval_started = time.perf_counter()
    generation_started = retrieval_started
    error_message = None

    try:
        predicted_intent = await adapter.predict_intent(case.input_query)
        predicted_tool = adapter.select_tool(predicted_intent)
        predicted_agent = adapter.select_agent(predicted_intent)

        if evidence_mode == "live":
            retrieved_contexts = adapter.retrieve_contexts(case.input_query, limit=3)
            retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000.0
            generation_started = time.perf_counter()
            generated_answer = adapter.generate_answer(case.to_dict(), retrieved_contexts)
        else:
            retrieved_contexts = case.expected_retrieved_context
            retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000.0
            generation_started = time.perf_counter()
            generated_answer = case.reference_answer

        generation_latency_ms = (time.perf_counter() - generation_started) * 1000.0
    except Exception as exc:
        error_message = str(exc)
        predicted_intent = "general"
        predicted_tool = adapter.select_tool(predicted_intent)
        predicted_agent = adapter.select_agent(predicted_intent)
        retrieved_contexts = []
        generated_answer = "I could not complete this task because of an internal error."
        retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000.0
        generation_latency_ms = 0.0

    latency_ms = (time.perf_counter() - started) * 1000.0

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
    task_specific_score = score_task_specific(
        category=case.category,
        query=case.input_query,
        generated_answer=generated_answer,
        reference_answer=case.reference_answer,
        retrieved_contexts=retrieved_contexts,
        expected_contexts=case.expected_retrieved_context,
    )
    hallucination_score = evaluate_hallucination(generated_answer, retrieved_contexts)
    tool_selection_accuracy = evaluate_tool_selection(case.expected_tool, predicted_tool)
    routing_accuracy = evaluate_routing(case.expected_agent, predicted_agent)
    error_handling_score = score_error_handling(error_message, generated_answer)

    input_tokens = estimate_token_count(case.input_query) + sum(estimate_token_count(context) for context in retrieved_contexts)
    output_tokens = estimate_token_count(generated_answer)
    estimated_tokens = input_tokens + output_tokens
    estimated_cost_units = estimate_cost_units(input_tokens, output_tokens)
    cost_efficiency = score_cost_efficiency(estimated_cost_units)
    latency_efficiency = score_latency_efficiency(latency_ms)

    score_bundle = compute_final_score(
        rag_quality=rag_metrics["rag_quality"],
        answer_quality=answer_metrics["answer_quality"],
        hallucination_score=hallucination_score,
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
        task_specific_score=task_specific_score,
        error_handling_score=error_handling_score,
        cost_efficiency=cost_efficiency,
        latency_efficiency=latency_efficiency,
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
        task_specific_score=task_specific_score,
        error_handling_score=error_handling_score,
        hallucination_score=hallucination_score,
        hallucination_penalty=score_bundle["hallucination_penalty"],
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
        estimated_tokens=estimated_tokens,
        estimated_cost_units=estimated_cost_units,
        latency_ms=latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        error_message=error_message,
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
    task_specific_score = mean(result.task_specific_score for result in results)
    error_handling_score = mean(result.error_handling_score for result in results)
    hallucination_penalty = mean(result.hallucination_penalty for result in results)
    tool_selection_accuracy = mean(result.tool_selection_accuracy for result in results)
    routing_accuracy = mean(result.routing_accuracy for result in results)
    estimated_tokens = mean(result.estimated_tokens for result in results)
    estimated_cost_units = mean(result.estimated_cost_units for result in results)
    latency_ms = mean(result.latency_ms for result in results)
    retrieval_latency_ms = mean(result.retrieval_latency_ms for result in results)
    generation_latency_ms = mean(result.generation_latency_ms for result in results)
    final_score = mean(result.final_score for result in results)
    passed = final_score >= pass_threshold

    report = EvaluationReport(
        dataset_name=str(dataset_payload.get("dataset_name", "evaluation_dataset")),
        evaluation_version=EVALUATION_VERSION,
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
        task_specific_score=task_specific_score,
        error_handling_score=error_handling_score,
        hallucination_penalty=hallucination_penalty,
        tool_selection_accuracy=tool_selection_accuracy,
        routing_accuracy=routing_accuracy,
        estimated_tokens=estimated_tokens,
        estimated_cost_units=estimated_cost_units,
        latency_ms=latency_ms,
        retrieval_latency_ms=retrieval_latency_ms,
        generation_latency_ms=generation_latency_ms,
        passed=passed,
        cases=results,
        prompt_versions=prompt_versions(),
        meta=dataset_payload.get("meta", {}),
    )

    report.meta = {
        **report.meta,
        "evaluation_version": EVALUATION_VERSION,
        "dataset_version": dataset_payload.get("dataset_name", EVALUATION_DATASET_VERSION),
        "prompt_registry_version": PROMPT_REGISTRY_VERSION,
        "prompt_versions": prompt_versions(),
    }

    results_path.write_text(json.dumps(report.to_dict(), indent=2))
    version_manifest_path = results_path.with_name("version-manifest.json")
    version_manifest = build_version_manifest(
        dataset_name=str(dataset_payload.get("dataset_name", EVALUATION_DATASET_VERSION)),
        meta=report.meta,
    )
    version_manifest_path.write_text(json.dumps(version_manifest, indent=2))
    _print_summary(report)
    return report


def _print_summary(report: EvaluationReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print("\n=== FamilyOps Evaluation Summary ===")
    print(f"Dataset: {report.dataset_name}")
    print(f"Evaluation version: {report.evaluation_version}")
    print(f"Prompt registry: {report.meta.get('prompt_registry_version', 'unknown')}")
    print(f"Cases: {report.total_cases}")
    print(f"Final score: {report.final_score:.3f} (threshold {report.pass_threshold:.2f})")
    print(f"RAG quality: {report.rag_quality:.3f}")
    print(f"Context precision: {report.rag_metrics['context_precision']:.3f}")
    print(f"Context recall: {report.rag_metrics['context_recall']:.3f}")
    print(f"Faithfulness: {report.rag_metrics['faithfulness']:.3f}")
    print(f"Answer relevancy: {report.rag_metrics['answer_relevance']:.3f}")
    print(f"Answer quality: {report.answer_quality:.3f}")
    print(f"Task specific: {report.task_specific_score:.3f}")
    print(f"Error handling: {report.error_handling_score:.3f}")
    print(f"Hallucination penalty: {report.hallucination_penalty:.3f}")
    print(f"Tool selection accuracy: {report.tool_selection_accuracy:.3f}")
    print(f"Routing accuracy: {report.routing_accuracy:.3f}")
    print(f"Estimated tokens: {report.estimated_tokens:.1f}")
    print(f"Estimated cost units: {report.estimated_cost_units:.3f}")
    print(f"Latency ms: {report.latency_ms:.1f}")
    print(f"Retrieval latency ms: {report.retrieval_latency_ms:.1f}")
    print(f"Generation latency ms: {report.generation_latency_ms:.1f}")
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
