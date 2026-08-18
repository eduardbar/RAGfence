"""Tests for the frozen canonical score contract."""

import pytest

from ragfence.evaluation.contracts import MetricValue
from ragfence.evaluation.scoring import calculate_score, passes_threshold


def test_score_is_clamped_and_rounded_to_two_decimal_places() -> None:
    assert calculate_score({"quality": MetricValue("quality", 2.0)}) == 100.0
    assert calculate_score({"quality": MetricValue("quality", -1.0)}) == 0.0
    assert calculate_score({"quality": MetricValue("quality", 0.12345)}) == 12.35


def test_score_uses_weighted_mean_and_excludes_unavailable_metrics() -> None:
    metrics = {
        "quality": MetricValue("quality", 0.8),
        "security": MetricValue.unavailable("security", "not measured"),
    }

    assert calculate_score(metrics, weights={"quality": 1.0, "security": 1.0}) == 80.0


def test_threshold_equality_passes_on_canonical_scale() -> None:
    assert passes_threshold(80.0, 80.0) is True
    assert passes_threshold(79.99, 80.0) is False


def test_invalid_threshold_is_rejected() -> None:
    with pytest.raises(ValueError, match="threshold"):
        passes_threshold(50, 100.01)


@pytest.mark.parametrize("weight", [float("inf"), float("-inf")])
def test_infinite_metric_weights_are_rejected(weight: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        calculate_score({"quality": MetricValue("quality", 0.5)}, weights={"quality": weight})
