"""Canonical, deterministic evaluation report artifacts.

The report seam accepts the engine's public summary/result-shaped values without
requiring the engine to depend on a renderer.  It deliberately omits volatile
fields unless a caller injects a timestamp.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from typing import Any, cast

from ragfence.evaluation.redaction import bounded_text, redact_evidence, safe_id


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dict(dumped)
    if is_dataclass(value):
        return asdict(cast(Any, value))
    return {
        name: getattr(value, name)
        for name in ("id", "case_id", "passed", "findings", "retrieved", "answer", "latency_ms")
        if hasattr(value, name)
    }


def _value(value: object) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and not isinstance(value, Mapping):
        return value.value
    return safe_id(value)


def _metrics(summary: Mapping[str, Any]) -> dict[str, Any]:
    raw = summary.get("metrics", {})
    if isinstance(raw, Mapping):
        items = list(raw.items())
    else:
        items = [(getattr(metric, "name", "metric"), metric) for metric in raw]
    output: dict[str, Any] = {}
    for name, metric in items:
        if hasattr(metric, "value") and hasattr(metric, "available"):
            output[str(name)] = {
                "available": bool(metric.available),
                "policy": _value(getattr(metric, "policy", None)),
                "reason": getattr(metric, "reason", None),
                "value": getattr(metric, "value", None),
            }
        else:
            output[str(name)] = _value(metric)
    return {name: output[name] for name in sorted(output)}


def _finding(value: object) -> dict[str, Any]:
    finding = _mapping(value)
    result: dict[str, Any] = {
        "category": str(finding.get("category", "")),
        "description": bounded_text(finding.get("description", "")),
        "evidence": redact_evidence(finding.get("evidence", {})),
        "id": safe_id(finding.get("id", "")),
        "severity": _value(finding.get("severity", "")),
        "title": bounded_text(finding.get("title", "")),
    }
    return result


def _result(value: object) -> dict[str, Any]:
    result = _mapping(value)
    case = result.get("case")
    if case is not None and "case_id" not in result:
        result["case_id"] = _mapping(case).get("id", "")
    findings = result.get("findings", ()) or ()
    retrieved = result.get("retrieved", ()) or ()
    finding_values = [_finding(item) for item in findings]
    finding_values.sort(key=lambda item: (item["id"], item["category"], item["severity"]))
    chunk_ids = []
    for chunk in retrieved:
        chunk_map = _mapping(chunk)
        chunk_ids.append(safe_id(chunk_map.get("chunk_id", chunk_map.get("id", ""))))
    chunk_ids.sort()
    output: dict[str, Any] = {
        "case_id": safe_id(result.get("case_id", "")),
        "findings": finding_values,
        "latency_ms": max(0, int(result.get("latency_ms", 0))),
        "passed": bool(result.get("passed", False)),
        "retrieved": chunk_ids,
    }
    if result.get("answer") is not None:
        output["answer"] = bounded_text(result["answer"])
    return output


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Immutable canonical report payload."""

    payload: dict[str, Any]


def build_report(
    summary: object,
    results: Iterable[object],
    *,
    timestamp: datetime | str | None = None,
) -> EvaluationReport:
    """Build a stable report from engine summary and per-case results.

    Timestamps are intentionally absent by default.  Supplying one is the only
    way to add the ``timestamp`` field, making repeated renders byte-equivalent.
    """
    summary_map = _mapping(summary)
    normalized_results = [_result(item) for item in results]
    normalized_results.sort(key=lambda item: item["case_id"])
    payload: dict[str, Any] = {
        "metrics": _metrics(summary_map),
        "outcome": _value(summary_map.get("outcome", "")),
        "results": normalized_results,
        "score": summary_map.get("score", 0),
        "threshold": summary_map.get("threshold", 0),
    }
    if timestamp is not None:
        payload["timestamp"] = (
            timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
        )
    return EvaluationReport(payload)


def report_payload(report: EvaluationReport) -> dict[str, Any]:
    """Return the canonical payload without exposing mutable report internals."""
    encoded = json.dumps(report.payload, sort_keys=True, default=_value)
    return cast(dict[str, Any], json.loads(encoded))


def render_json(report: EvaluationReport) -> str:
    """Render canonical JSON with sorted keys and a stable trailing newline."""
    return json.dumps(report_payload(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_text(report: EvaluationReport) -> str:
    """Render a concise plain-text projection of the canonical artifact."""
    payload = report_payload(report)
    metrics = payload["metrics"]
    metric_text = ", ".join(f"{name}={value}" for name, value in metrics.items())
    return (
        "\n".join(
            [
                "RAGFence evaluation report",
                f"Score: {payload['score']}/100",
                f"Threshold: {payload['threshold']}/100",
                f"Outcome: {payload['outcome']}",
                f"Metrics: {metric_text}",
                f"Cases: {len(payload['results'])}",
            ]
        )
        + "\n"
    )
