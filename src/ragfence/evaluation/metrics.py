"""Pure, deterministic evaluation metric functions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from statistics import median
from typing import Any

from ragfence.evaluation.contracts import MetricValue


def _observation(item: object) -> object:
    return getattr(item, "observation", item)


def _case(item: object) -> object:
    return getattr(item, "case", item)


def _retrieved(item: object) -> Sequence[object]:
    return getattr(_observation(item), "retrieved", ())


def unauthorized_retrieval_rate(verdicts: Iterable[object]) -> float:
    """Return blocked-case observations with any retrieved chunk / all cases."""
    items = list(verdicts)
    if not items:
        return 0.0
    unauthorized = sum(
        bool(_retrieved(item)) and not bool(getattr(_case(item), "expected_allow", False))
        for item in items
    )
    return round(unauthorized / len(items), 12)


def leakage_rate(verdicts: Iterable[object], sensitive_markers: Iterable[str]) -> float:
    """Return answers containing a configured marker / all cases."""
    items = list(verdicts)
    markers = tuple(marker.casefold() for marker in sensitive_markers if marker)
    if not items:
        return 0.0
    leaked = sum(
        bool(markers)
        and any(
            marker in (getattr(_observation(item), "answer", "") or "").casefold()
            for marker in markers
        )
        for item in items
    )
    return round(leaked / len(items), 12)


def latency_summary(verdicts: Iterable[object]) -> dict[str, int | float]:
    """Return a stable latency summary, with mean rounded half-up by formatting."""
    values = sorted(max(0, int(getattr(_observation(item), "latency_ms", 0))) for item in verdicts)
    if not values:
        return {"count": 0, "min_ms": 0, "max_ms": 0, "mean_ms": 0.0, "p50_ms": 0.0}
    mean = round(sum(values) / len(values), 2)
    return {
        "count": len(values),
        "min_ms": values[0],
        "max_ms": values[-1],
        "mean_ms": mean,
        "p50_ms": float(median(values)),
    }


def _retrieved_ids(item: object) -> set[Any]:
    return {getattr(chunk, "chunk_id", None) for chunk in _retrieved(item)}


def _ground_truth_metric(
    name: str, verdicts: Sequence[object], relevant: Mapping[Any, Iterable[Any]], recall: bool
) -> MetricValue:
    if not verdicts or not relevant:
        return MetricValue.unavailable(name, "ground truth not supplied")
    ratios: list[float] = []
    for item in verdicts:
        case_id = getattr(_observation(item), "case_id", None)
        expected = set(relevant.get(case_id, ()))
        actual = _retrieved_ids(item)
        if recall:
            ratios.append(len(actual & expected) / len(expected) if expected else 0.0)
        else:
            ratios.append(len(actual & expected) / len(actual) if actual else 0.0)
    return MetricValue(name, round(sum(ratios) / len(ratios), 12))


def metric_set(
    verdicts: Iterable[object],
    *,
    relevant_chunk_ids_by_case: Mapping[Any, Iterable[Any]],
    provider_real: bool = False,
    generation_metrics: Mapping[str, float] | None = None,
    provider_metadata: Mapping[str, object] | None = None,
) -> dict[str, MetricValue]:
    """Build canonical metrics and gate generation metrics on real-provider evidence."""
    items = tuple(verdicts)
    unauthorized = unauthorized_retrieval_rate(items)
    generation = generation_metrics or {}
    faithfulness = (
        MetricValue("faithfulness", generation["faithfulness"])
        if provider_real and "faithfulness" in generation
        else MetricValue.unavailable(
            "faithfulness",
            "generation evidence not supplied" if provider_real else "skipped: no_real_provider",
        )
    )
    answer_correctness = (
        MetricValue("answer_correctness", generation["answer_correctness"])
        if provider_real and "answer_correctness" in generation
        else MetricValue.unavailable(
            "answer_correctness",
            "answer correctness evidence not supplied"
            if provider_real
            else "skipped: no_real_provider",
        )
    )
    values = {
        "context_precision": _ground_truth_metric(
            "context_precision", items, relevant_chunk_ids_by_case, False
        ),
        "context_recall": _ground_truth_metric(
            "context_recall", items, relevant_chunk_ids_by_case, True
        ),
        "unauthorized_retrieval_rate": MetricValue("unauthorized_retrieval_rate", unauthorized),
        "leakage_rate": MetricValue("leakage_rate", leakage_rate(items, ())),
        "faithfulness": faithfulness,
        "answer_correctness": answer_correctness,
        "latency_ms": (
            MetricValue(
                "latency_ms",
                round(
                    sum(max(0, int(getattr(_observation(item), "latency_ms", 0))) for item in items)
                    / len(items),
                    12,
                ),
            )
            if provider_real and items
            else MetricValue.unavailable("latency_ms", "latency requires a real provider")
        ),
        "cost_usd": MetricValue.unavailable("cost_usd", "adapter did not supply cost"),
    }
    metadata = provider_metadata or {}
    for name in ("prompt_tokens", "completion_tokens"):
        count = metadata.get(name)
        values[name] = (
            MetricValue(name, float(count))
            if provider_real and type(count) is int and count >= 0
            else MetricValue.unavailable(name, "provider token usage not supplied")
        )
    return values
