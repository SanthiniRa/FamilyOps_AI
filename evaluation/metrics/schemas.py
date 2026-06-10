from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationCase:
    id: str
    category: str
    input_query: str
    expected_intent_label: str
    expected_tool: str
    expected_agent: str
    expected_retrieved_context: List[str]
    reference_answer: str
    expected_routing_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "EvaluationCase":
        return cls(
            id=payload["id"],
            category=payload["category"],
            input_query=payload["input_query"],
            expected_intent_label=payload["expected_intent_label"],
            expected_tool=payload["expected_tool"],
            expected_agent=payload["expected_agent"],
            expected_retrieved_context=list(payload.get("expected_retrieved_context", [])),
            reference_answer=payload["reference_answer"],
            expected_routing_path=list(payload.get("expected_routing_path", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "input_query": self.input_query,
            "expected_intent_label": self.expected_intent_label,
            "expected_tool": self.expected_tool,
            "expected_agent": self.expected_agent,
            "expected_retrieved_context": self.expected_retrieved_context,
            "reference_answer": self.reference_answer,
            "expected_routing_path": self.expected_routing_path,
            "metadata": self.metadata,
        }


@dataclass
class EvaluationCaseResult:
    case_id: str
    category: str
    input_query: str
    expected_intent_label: str
    predicted_intent_label: str
    expected_tool: str
    predicted_tool: str
    expected_agent: str
    predicted_agent: str
    retrieved_contexts: List[str]
    reference_answer: str
    generated_answer: str
    rag_metrics: Dict[str, float]
    answer_metrics: Dict[str, float]
    task_specific_score: float
    error_handling_score: float
    hallucination_score: float
    hallucination_penalty: float
    tool_selection_accuracy: float
    routing_accuracy: float
    estimated_tokens: int
    estimated_cost_units: float
    latency_ms: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    error_message: Optional[str]
    final_score: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "input_query": self.input_query,
            "expected_intent_label": self.expected_intent_label,
            "predicted_intent_label": self.predicted_intent_label,
            "expected_tool": self.expected_tool,
            "predicted_tool": self.predicted_tool,
            "expected_agent": self.expected_agent,
            "predicted_agent": self.predicted_agent,
            "retrieved_contexts": self.retrieved_contexts,
            "reference_answer": self.reference_answer,
            "generated_answer": self.generated_answer,
            "rag_metrics": self.rag_metrics,
            "answer_metrics": self.answer_metrics,
            "task_specific_score": self.task_specific_score,
            "error_handling_score": self.error_handling_score,
            "hallucination_score": self.hallucination_score,
            "hallucination_penalty": self.hallucination_penalty,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "routing_accuracy": self.routing_accuracy,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_units": self.estimated_cost_units,
            "latency_ms": self.latency_ms,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
            "error_message": self.error_message,
            "final_score": self.final_score,
        }


@dataclass
class EvaluationReport:
    dataset_name: str
    evaluation_version: str
    total_cases: int
    pass_threshold: float
    final_score: float
    rag_quality: float
    rag_metrics: Dict[str, float]
    answer_quality: float
    task_specific_score: float
    error_handling_score: float
    hallucination_penalty: float
    tool_selection_accuracy: float
    routing_accuracy: float
    estimated_tokens: float
    estimated_cost_units: float
    latency_ms: float
    retrieval_latency_ms: float
    generation_latency_ms: float
    passed: bool
    cases: List[EvaluationCaseResult]
    prompt_versions: Dict[str, str] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "evaluation_version": self.evaluation_version,
            "prompt_versions": self.prompt_versions,
            "total_cases": self.total_cases,
            "pass_threshold": self.pass_threshold,
            "final_score": self.final_score,
            "rag_quality": self.rag_quality,
            "rag_metrics": self.rag_metrics,
            "answer_quality": self.answer_quality,
            "task_specific_score": self.task_specific_score,
            "error_handling_score": self.error_handling_score,
            "hallucination_penalty": self.hallucination_penalty,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "routing_accuracy": self.routing_accuracy,
            "estimated_tokens": self.estimated_tokens,
            "estimated_cost_units": self.estimated_cost_units,
            "latency_ms": self.latency_ms,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
            "passed": self.passed,
            "cases": [case.to_dict() for case in self.cases],
            "meta": self.meta,
        }
