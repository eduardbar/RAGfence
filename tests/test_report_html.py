"""Standalone HTML report viewer contract tests."""

import json
from pathlib import Path

from typer.testing import CliRunner

from ragfence.cli import main
from ragfence.cli.report_html import render_html

runner = CliRunner()


def _payload(outcome: str = "pass") -> dict:
    return {
        "overall_score": 0.9,
        "security_score": 0.95,
        "utility_score": 0.85,
        "outcome": outcome,
        "controls": [
            {"id": "auth-read", "category": "authorization", "status": "pass", "reason": "allowed"}
        ],
        "findings": [{"title": "Unsafe input", "description": "<script>alert(1)</script>"}],
        "timestamp": "2026-08-22T10:00:00Z",
    }


def test_render_html_is_complete_escaped_and_contains_report_sections() -> None:
    rendered = render_html(_payload())

    assert rendered.startswith("<!doctype html>")
    assert "<html" in rendered
    assert '<meta charset="utf-8">' in rendered
    assert 'class="outcome-pass"' in rendered
    assert "0.9" in rendered
    assert "0.95" in rendered
    assert "0.85" in rendered
    assert "auth-read" in rendered
    assert "authorization" in rendered
    assert "allowed" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert "2026-08-22T10:00:00Z" in rendered
    assert "<footer>" in rendered


def test_render_html_uses_fail_badge() -> None:
    rendered = render_html(_payload("FAIL"))

    assert 'class="outcome-fail"' in rendered
    assert 'class="outcome-pass"' not in rendered


def test_report_command_writes_html_next_to_input(tmp_path: Path) -> None:
    source = tmp_path / "evidence.json"
    source.write_text(json.dumps(_payload()), encoding="utf-8")

    result = runner.invoke(main.app, ["report", str(source)])

    assert result.exit_code == 0
    destination = tmp_path / "evidence.html"
    assert destination.is_file()
    assert destination.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert str(destination) in result.output


def test_report_command_supports_output_and_open(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "evidence.json"
    destination = tmp_path / "viewer" / "result.html"
    source.write_text(json.dumps(_payload()), encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(main.webbrowser, "open", lambda value: opened.append(value))

    result = runner.invoke(
        main.app, ["report", str(source), "--output", str(destination), "--open"]
    )

    assert result.exit_code == 0
    assert destination.is_file()
    assert opened == [destination.resolve().as_uri()]


def test_report_command_missing_or_invalid_path_exits_two(tmp_path: Path) -> None:
    missing = runner.invoke(main.app, ["report", str(tmp_path / "missing.json")])
    assert missing.exit_code == 2
    assert "cannot read report" in missing.output
    assert "missing.json" in missing.output

    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    result = runner.invoke(main.app, ["report", str(invalid)])
    assert result.exit_code == 2
    assert "invalid report" in result.output
    assert "Traceback" not in result.output
