from pathlib import Path

from typer.testing import CliRunner

from ragfence.cli.main import app
from ragfence.cli.reporting import EvaluationReport, find_regressions, render_text

runner = CliRunner()


def _report(*, passed: bool = True, controls: list[dict] | None = None) -> EvaluationReport:
    return EvaluationReport(
        score=100.0,
        threshold=80.0,
        outcome="pass" if passed else "fail",
        findings=[],
        artifact={
            "controls": controls or [],
            "gate_passed": passed,
            "results": [],
            "score": 100.0,
            "threshold": 80.0,
            "outcome": "pass" if passed else "fail",
        },
    )


def test_find_regressions_only_matches_baseline_pass_controls() -> None:
    baseline = {"controls": [
        {"id": "a", "status": "pass"},
        {"id": "b", "status": "fail"},
        {"id": "c", "status": "pass"},
    ], "gate_passed": True}
    current = _report(controls=[
        {"id": "a", "status": "inconclusive"},
        {"id": "b", "status": "pass"},
        {"id": "c", "status": "skipped"},
        {"id": "new", "status": "fail"},
    ])

    assert find_regressions(baseline, current) == [
        {"control_id": "a", "from": "pass", "to": "inconclusive"},
        {"control_id": "c", "from": "pass", "to": "skipped"},
    ]


def test_gate_regression_is_reported() -> None:
    baseline = {"controls": [], "gate_passed": True}
    current = _report(passed=False)
    assert find_regressions(baseline, current) == [
        {"control_id": "gate", "from": "pass", "to": "fail"}
    ]


def test_text_report_lists_regressions_only_when_present() -> None:
    report = _report(controls=[])
    report.artifact["regressions"] = [
        {"control_id": "auth", "from": "pass", "to": "fail"}
    ]
    assert "REGRESSION auth: pass -> fail" in render_text(report)


def test_cli_writes_regressions_and_fails_even_when_gate_passes(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text('threshold = 0.8\nadapter = "reference"\n', encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        '{"controls": [{"id": "auth", "status": "pass"}], "gate_passed": true}',
        encoding="utf-8",
    )
    destination = tmp_path / "result.json"
    monkeypatch.setattr("ragfence.cli.main.evaluate", lambda *args, **kwargs: _report(
        controls=[{"id": "auth", "status": "fail"}]
    ))

    result = runner.invoke(app, [
        "test", "--config", str(config), "--baseline", str(baseline),
        "--json", "--output", str(destination),
    ])

    assert result.exit_code == 1
    assert "REGRESSION auth: pass -> fail" in result.output
    assert '"regressions"' in destination.read_text(encoding="utf-8")


def test_missing_baseline_is_exit_two_and_mentions_path(tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text('threshold = 0.8\nadapter = "reference"\n', encoding="utf-8")
    baseline = tmp_path / "missing.json"

    result = runner.invoke(app, ["test", "--config", str(config), "--baseline", str(baseline)])

    assert result.exit_code == 2
    assert str(baseline) in result.output


def test_unparseable_baseline_is_exit_two_and_mentions_path(tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text('threshold = 0.8\nadapter = "reference"\n', encoding="utf-8")
    baseline = tmp_path / "bad.json"
    baseline.write_text("not json", encoding="utf-8")

    result = runner.invoke(app, ["test", "--config", str(config), "--baseline", str(baseline)])

    assert result.exit_code == 2
    assert str(baseline) in result.output
