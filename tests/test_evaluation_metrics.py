"""Tests for deterministic evaluation metrics."""

from dataclasses import dataclass
from uuid import uuid4

from ragfence.evaluation.contracts import UnavailableMetricPolicy
from ragfence.evaluation.metrics import (
    latency_summary,
    leakage_rate,
    metric_set,
    unauthorized_retrieval_rate,
)


@dataclass(frozen=True)
class Observation:
    case_id: object
    retrieved: tuple[object, ...]
    answer: str | None
    error: str | None
    latency_ms: int


@dataclass(frozen=True)
class Verdict:
    case: object
    observation: Observation


def verdict(*, retrieved: int = 0, answer: str | None = None, latency: int = 0) -> Verdict:
    case_id = uuid4()
    chunks = tuple(object() for _ in range(retrieved))
    return Verdict(object(), Observation(case_id, chunks, answer, None, latency))


def test_security_rates_use_cases_as_denominator() -> None:
    values = [verdict(retrieved=1, answer="safe"), verdict(answer="SECRET marker")]

    assert unauthorized_retrieval_rate(values) == 0.5
    assert leakage_rate(values, sensitive_markers=("secret",)) == 0.5


def test_empty_inputs_are_zero_for_security_rates() -> None:
    assert unauthorized_retrieval_rate(()) == 0.0
    assert leakage_rate((), sensitive_markers=("secret",)) == 0.0


def test_latency_summary_is_deterministic_and_rounded() -> None:
    summary = latency_summary([verdict(latency=1), verdict(latency=2), verdict(latency=4)])

    assert summary == {"count": 3, "min_ms": 1, "max_ms": 4, "mean_ms": 2.33, "p50_ms": 2.0}


def test_metric_set_contains_explicit_unavailable_metric() -> None:
    values = metric_set([], relevant_chunk_ids_by_case={})

    assert values["context_precision"].available is False
    assert values["context_recall"].available is False


def test_metric_set_exposes_generation_and_optional_cost_metrics_as_unavailable() -> None:
    values = metric_set([], relevant_chunk_ids_by_case={})

    for name in ("faithfulness", "answer_correctness", "cost_usd"):
        assert values[name].available is False
        assert values[name].value is None
        assert values[name].policy is UnavailableMetricPolicy.EXCLUDE
        assert values[name].reason
