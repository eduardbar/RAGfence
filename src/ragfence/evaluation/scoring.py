"""Frozen, deterministic canonical score calculations."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Final

from ragfence.evaluation.contracts import (
    CANONICAL_SCORE_MAX,
    CANONICAL_SCORE_MIN,
    MetricValue,
    UnavailableMetricPolicy,
)

DEFAULT_WEIGHTS: Final[dict[str, float]] = {
    "context_precision": 1.0,
    "context_recall": 1.0,
    "faithfulness": 1.0,
    "answer_correctness": 1.0,
    "unauthorized_retrieval_rate": 2.0,
    "leakage_rate": 2.0,
}
_SECURITY_RATES = frozenset({"unauthorized_retrieval_rate", "leakage_rate"})


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _score_round(value: float) -> float:
    bounded = max(CANONICAL_SCORE_MIN, min(CANONICAL_SCORE_MAX, value))
    return float(Decimal(str(bounded)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def calculate_score(
    metrics: Mapping[str, MetricValue], *, weights: Mapping[str, float] | None = None
) -> float:
    """Calculate a weighted normalized mean on the inclusive 0–100 scale.

    Unavailable metrics are excluded by default, or contribute neutral ``0.5``
    only when explicitly marked with :class:`UnavailableMetricPolicy.NEUTRAL`.
    Security rates are inverted because zero is the secure target.
    """
    selected = (
        {name: DEFAULT_WEIGHTS.get(name, 1.0) for name in metrics} if weights is None else weights
    )
    total = 0.0
    denominator = 0.0
    for name, weight in selected.items():
        if weight < 0 or not isfinite(weight):
            raise ValueError("metric weights must be non-negative finite numbers")
        metric = metrics.get(name)
        if metric is None or not metric.available:
            if metric is None or metric.policy is UnavailableMetricPolicy.EXCLUDE:
                continue
            contribution = 0.5
        else:
            if metric.value is None:
                continue
            contribution = _clamp(metric.value)
            if name in _SECURITY_RATES:
                contribution = 1.0 - contribution
        total += contribution * weight
        denominator += weight
    if denominator == 0:
        return 0.0
    return _score_round(total / denominator * 100.0)


def passes_threshold(score: float, threshold: float) -> bool:
    """Return whether a canonical score meets its threshold; equality passes."""
    if not CANONICAL_SCORE_MIN <= threshold <= CANONICAL_SCORE_MAX:
        raise ValueError("threshold must be between 0 and 100")
    if not CANONICAL_SCORE_MIN <= score <= CANONICAL_SCORE_MAX:
        raise ValueError("score must be between 0 and 100")
    return score >= threshold


# Concise aliases for callers that use the domain vocabulary.
score_metrics = calculate_score
threshold_passed = passes_threshold
