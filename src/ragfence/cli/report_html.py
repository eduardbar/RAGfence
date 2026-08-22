"""Self-contained HTML rendering for JSON evaluation reports."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from typing import Any

_STYLE = """
:root { color-scheme: light; font-family: system-ui, sans-serif; }
body { background: #f5f7fa; color: #172033; margin: 0; }
main { margin: 0 auto; max-width: 1100px; padding: 2rem; }
header, section, footer { background: #fff; border: 1px solid #d8dee9;
  border-radius: .5rem; margin-bottom: 1.25rem; padding: 1.25rem; }
h1 { margin-top: 0; }
.score-grid { display: grid; gap: 1rem; grid-template-columns: repeat(3, 1fr); }
.score { background: #eef2f7; border-radius: .35rem; padding: 1rem; }
.score strong { display: block; font-size: 1.5rem; margin-top: .25rem; }
.outcome { border-radius: .35rem; display: inline-block; font-weight: 700; padding: .4rem .75rem; }
.outcome-pass { background: #d9f7e3; color: #12652f; }
.outcome-fail { background: #ffe0e0; color: #9b1c1c; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #d8dee9; padding: .7rem; text-align: left;
  vertical-align: top; }
th { background: #eef2f7; }
.status { font-weight: 700; }
footer { color: #536176; font-size: .9rem; }
@media (max-width: 700px) { .score-grid { grid-template-columns: 1fr; } main { padding: 1rem; } }
"""


def _text(value: object, default: str = "—") -> str:
    """Convert a report value to escaped text for an HTML text context."""
    return escape(default if value is None else str(value), quote=True)


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _findings(payload: dict[str, Any]) -> list[object]:
    direct = payload.get("findings")
    if isinstance(direct, list):
        return direct
    findings: list[object] = []
    for result in _items(payload.get("results")):
        if isinstance(result, dict):
            findings.extend(_items(result.get("findings")))
    return findings


def _finding_content(finding: object) -> tuple[str, str]:
    if not isinstance(finding, dict):
        return "Finding", str(finding)
    title = finding.get("title", finding.get("category", "Finding"))
    description = finding.get("description", finding.get("message", ""))
    return str(title), str(description)


def _score(payload: dict[str, Any], name: str) -> object:
    if name == "overall_score":
        return payload.get(name, payload.get("score"))
    return payload.get(name)


def render_html(report_payload: dict[str, Any]) -> str:
    """Render a report payload as a complete, escaped, standalone HTML document."""
    outcome = str(report_payload.get("outcome", "fail")).lower()
    passed = outcome == "pass"
    outcome_class = "outcome-pass" if passed else "outcome-fail"
    outcome_label = "PASS" if passed else "FAIL"
    timestamp = report_payload.get("timestamp", report_payload.get("generated_at"))
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat()

    controls = _items(report_payload.get("controls"))
    control_rows: list[str] = []
    for control in controls:
        if not isinstance(control, dict):
            continue
        status = control.get("status")
        control_rows.append(
            "<tr>"
            f"<td>{_text(control.get('id'))}</td>"
            f"<td>{_text(control.get('category'))}</td>"
            f'<td><span class="status">{_text(status)}</span></td>'
            f"<td>{_text(control.get('reason'))}</td>"
            "</tr>"
        )
    if not control_rows:
        control_rows.append('<tr><td colspan="4">No controls reported.</td></tr>')

    finding_items: list[str] = []
    for finding in _findings(report_payload):
        title, description = _finding_content(finding)
        finding_items.append(f"<li><strong>{_text(title)}</strong>: {_text(description)}</li>")
    if not finding_items:
        finding_items.append("<li>No findings reported.</li>")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RAGFence Security Report</title>
<style>{_STYLE}</style>
</head>
<body>
<main>
<header>
<h1>RAGFence Security Report</h1>
<p class="{outcome_class}">Outcome: {outcome_label}</p>
<div class="score-grid">
<div class="score">Overall score<strong>{
        _text(_score(report_payload, "overall_score"))
    }</strong></div>
<div class="score">Security score<strong>{
        _text(_score(report_payload, "security_score"))
    }</strong></div>
<div class="score">Utility score<strong>{
        _text(_score(report_payload, "utility_score"))
    }</strong></div>
</div>
</header>
<section>
<h2>Controls</h2>
<table>
<thead><tr><th>ID</th><th>Category</th><th>Status</th><th>Reason</th></tr></thead>
<tbody>{"".join(control_rows)}</tbody>
</table>
</section>
<section>
<h2>Findings</h2>
<ul>{"".join(finding_items)}</ul>
</section>
<footer>Generated: {_text(timestamp)}</footer>
</main>
</body>
</html>
"""
