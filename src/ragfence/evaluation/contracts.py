"""Immutable value contracts shared by evaluation work units."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Final

CANONICAL_SCORE_MIN: Final[float] = 0.0
CANONICAL_SCORE_MAX: Final[float] = 100.0


class UnavailableMetricPolicy(StrEnum):
    """How a metric with no defensible input is handled by scoring."""

    EXCLUDE = "exclude"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class MetricValue:
    """A named normalized metric, or an explicitly unavailable metric."""

    name: str
    value: float | None
    available: bool = True
    reason: str | None = None
    policy: UnavailableMetricPolicy = UnavailableMetricPolicy.EXCLUDE

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("metric name must not be empty")
        if self.value is not None and not isfinite(self.value):
            raise ValueError("metric value must be finite")
        if self.available and self.value is None:
            raise ValueError("available metric must have a value")
        if not self.available and not self.reason:
            raise ValueError("unavailable metric requires a reason")

    @classmethod
    def unavailable(
        cls,
        name: str,
        reason: str,
        policy: UnavailableMetricPolicy = UnavailableMetricPolicy.EXCLUDE,
    ) -> MetricValue:
        return cls(name, None, False, reason, policy)


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Stable ordered collection of metric values for a report or score."""

    values: tuple[MetricValue, ...]

    def as_dict(self) -> dict[str, MetricValue]:
        return {metric.name: metric for metric in self.values}
