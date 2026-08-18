"""Reporting and initialization contract tests for the Phase 6 CLI."""

import json
from pathlib import Path

from typer.testing import CliRunner

from ragfence.cli import main
from ragfence.cli.main import app
from ragfence.cli.reporting import EvaluationReport, render_json, render_text, write_report

runner = CliRunner()


def _report() -> EvaluationReport:
    return EvaluationReport(
        score=0.72,
        threshold=0.8,
        outcome="FAIL",
        findings=[
            {"message": "Authorization header: Bearer secret-token", "chunk_content": "private"}
        ],
    )


def test_text_report_redacts_secrets_and_has_no_ansi() -> None:
    output = render_text(_report())

    assert "secret-token" not in output
    assert "private" not in output
    assert "0.72" in output
    assert "\x1b[" not in output


def test_json_report_is_valid_and_redacted() -> None:
    payload = json.loads(render_json(_report()))

    assert payload["score"] == 0.72
    assert payload["threshold"] == 0.8
    assert "secret-token" not in json.dumps(payload)
    assert "private" not in json.dumps(payload)


def test_write_report_creates_parent_and_json(tmp_path: Path) -> None:
    destination = tmp_path / ".ragfence" / "reports" / "result.json"

    written = write_report(_report(), destination, json_output=True)

    assert written == destination
    assert json.loads(destination.read_text(encoding="utf-8"))["outcome"] == "FAIL"


def test_init_creates_config_and_report_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "ragfence.toml").is_file()
    assert (tmp_path / ".ragfence" / "reports").is_dir()


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("custom = true\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--path", str(tmp_path)])

    assert result.exit_code == 2
    assert config.read_text(encoding="utf-8") == "custom = true\n"


def test_test_command_passes_and_writes_json(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    monkeypatch.setattr(
        main, "evaluate", lambda *_args, **_kwargs: EvaluationReport(0.9, 0.8, "PASS", [])
    )

    result = runner.invoke(app, ["test", "--config", str(config), "--json"])

    assert result.exit_code == 0
    assert '"outcome": "PASS"' in result.output
    assert (tmp_path / ".ragfence" / "reports" / "latest.json").is_file()


def test_test_command_returns_one_below_threshold(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    monkeypatch.setattr(
        main, "evaluate", lambda *_args, **_kwargs: EvaluationReport(0.7, 0.8, "FAIL", [])
    )

    result = runner.invoke(app, ["test", "--config", str(config)])

    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_test_command_maps_runtime_error_to_two(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")

    def fail(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "evaluate", fail)
    result = runner.invoke(app, ["test", "--config", str(config)])

    assert result.exit_code == 2
    assert "command failed" in result.output


def test_adapter_check_maps_unavailable_target_to_two(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "check_adapter",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )

    result = runner.invoke(app, ["adapter", "check", "generic_http", "--base-url", "http://stub"])

    assert result.exit_code == 2
    assert "command failed" in result.output


def test_demo_maps_unavailable_service_to_two(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "check_demo",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")),
    )

    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 2
    assert "command failed" in result.output
