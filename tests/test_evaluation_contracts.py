"""Contracts for the deterministic evaluation seam."""

from dataclasses import FrozenInstanceError

import pytest

from ragfence.evaluation.contracts import (
    CANONICAL_SCORE_MAX,
    CANONICAL_SCORE_MIN,
    EvaluationMetrics,
    MetricValue,
    UnavailableMetricPolicy,
)


def test_metric_value_can_explicitly_represent_unavailable_data() -> None:
    metric = MetricValue.unavailable("context_precision", "ground truth not supplied")

    assert metric.name == "context_precision"
    assert metric.value is None
    assert metric.available is False
    assert metric.reason == "ground truth not supplied"
    assert metric.policy is UnavailableMetricPolicy.EXCLUDE


def test_metric_value_is_immutable_and_score_bounds_are_frozen() -> None:
    metrics = EvaluationMetrics(values=(MetricValue("latency_ms", 12.345),))

    assert (CANONICAL_SCORE_MIN, CANONICAL_SCORE_MAX) == (0, 100)
    with pytest.raises(FrozenInstanceError):
        metrics.values = ()  # type: ignore[misc]


def test_metric_value_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="finite"):
        MetricValue("latency_ms", float("nan"))
