"""Deterministic, redacted report rendering for the RAGFence CLI."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

_SECRET_PATTERN = re.compile(r"(?i)(bearer\s+|api[_-]?key\s*[=:]\s*)[^\s,;]+")
_REDACTED_KEYS = {"chunk_content", "content", "authorization", "authorization_header"}


@dataclass(frozen=True)
class EvaluationReport:
    """Minimal report contract shared by CLI and evaluation layers."""

    score: float
    threshold: float
    outcome: str
    findings: list[dict[str, Any]]
    artifact: dict[str, Any] | None = None


def _redact(value: Any, *, key: str | None = None) -> Any:
    if key in _REDACTED_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(name): _redact(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r"\1[REDACTED]", value)
    return value


def report_payload(report: EvaluationReport) -> dict[str, Any]:
    """Return the public, redacted report payload."""
    if report.artifact is not None:
        return cast(dict[str, Any], _redact(report.artifact))
    return cast(dict[str, Any], _redact(asdict(report)))


def render_json(report: EvaluationReport) -> str:
    """Render a stable JSON report."""
    return json.dumps(report_payload(report), indent=2, sort_keys=True) + "\n"


def render_text(report: EvaluationReport) -> str:
    """Render a plain-text report without terminal control sequences."""
    payload = report_payload(report)
    if "results" in payload:
        lines = [
            "RAGFence evaluation report",
            f"Score: {payload['score']}/100",
            f"Threshold: {payload['threshold']}/100",
            f"Outcome: {payload['outcome']}",
            f"Cases: {len(payload['results'])}",
        ]
        lines.extend(
            f"REGRESSION {item['control_id']}: {item['from']} -> {item['to']}"
            for item in payload.get("regressions", [])
        )
        return "\n".join(lines) + "\n"
    lines = [
        "RAGFence evaluation report",
        f"Score: {payload['score']}",
        f"Threshold: {payload['threshold']}",
        f"Outcome: {payload['outcome']}",
        f"Findings: {len(payload['findings'])}",
    ]
    for index, finding in enumerate(payload["findings"], start=1):
        message = finding.get("message", "finding") if isinstance(finding, dict) else "finding"
        lines.append(f"{index}. {message}")
    return "\n".join(lines) + "\n"


def load_baseline(path: Path) -> dict[str, Any]:
    """Load and minimally validate a previous JSON report."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load baseline report '{path}': {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("controls"), list):
        raise ValueError(
            f"cannot load baseline report '{path}': expected a JSON report with controls"
        )
    return payload


def find_regressions(baseline: dict[str, Any], current: EvaluationReport) -> list[dict[str, str]]:
    """Compare baseline PASS controls and gate status with the current report."""
    baseline_controls = {
        str(item["id"]): str(item.get("status"))
        for item in baseline["controls"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    current_payload = report_payload(current)
    current_controls = {
        str(item["id"]): str(item.get("status"))
        for item in current_payload.get("controls", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    regressions: list[dict[str, str]] = []
    for control_id, before in baseline_controls.items():
        after = current_controls.get(control_id)
        if before == "pass" and after in {"fail", "inconclusive", "skipped"}:
            regressions.append({"control_id": control_id, "from": str(before), "to": str(after)})
    if baseline.get("gate_passed") is True and current_payload.get("gate_passed") is False:
        regressions.append({"control_id": "gate", "from": "pass", "to": "fail"})
    return regressions


def write_report(report: EvaluationReport, destination: Path, *, json_output: bool) -> Path:
    """Write a report, creating its parent directory.

    A ``.json`` destination always receives JSON, even without ``--json``:
    the report must stay machine-parseable when its extension promises it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    use_json = json_output or destination.suffix.lower() == ".json"
    content = render_json(report) if use_json else render_text(report)
    destination.write_text(content, encoding="utf-8")
    return destination
