"""Policy profile contract tests for the CLI."""

from pathlib import Path

from typer.testing import CliRunner

from ragfence.cli import main
from ragfence.cli.config import CliConfig, apply_profile
from ragfence.cli.reporting import EvaluationReport

runner = CliRunner()


def test_profiles_apply_exact_thresholds_in_cli_scale() -> None:
    settings = CliConfig(threshold=0.8)

    assert apply_profile(settings, "default").threshold == 0.8
    assert apply_profile(settings, "strict").threshold == 0.95
    assert apply_profile(CliConfig(threshold=0.99), "strict").threshold == 0.99
    assert apply_profile(settings, "permissive").threshold == 0.6
    assert apply_profile(CliConfig(threshold=0.4), "permissive").threshold == 0.4


def test_explicit_threshold_overrides_profile(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_evaluate(settings, **_kwargs):
        seen["threshold"] = settings.threshold
        return EvaluationReport(100.0, settings.threshold * 100, "PASS", [])

    monkeypatch.setattr(main, "evaluate", fake_evaluate)

    result = runner.invoke(
        main.app,
        ["test", "--config", str(config), "--profile", "strict", "--threshold", "0.7"],
    )

    assert result.exit_code == 0
    assert seen["threshold"] == 0.7


def test_strict_profile_fails_with_non_passing_control_ids(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    report = EvaluationReport(
        100.0,
        95.0,
        "PASS",
        [],
        artifact={
            "score": 100.0,
            "threshold": 95.0,
            "outcome": "PASS",
            "findings": [],
            "controls": [
                {"id": "allow-read", "status": "pass"},
                {"id": "deny-secret", "status": "fail"},
                {"id": "deny-unknown", "status": "inconclusive"},
            ],
        },
    )
    monkeypatch.setattr(main, "evaluate", lambda *_args, **_kwargs: report)

    result = runner.invoke(main.app, ["test", "--config", str(config), "--profile", "strict"])

    assert result.exit_code == 1
    assert "non-passing controls: deny-secret, deny-unknown" in result.output


def test_profile_help_documents_precedence() -> None:
    result = runner.invoke(main.app, ["test", "--help"])

    assert result.exit_code == 0
    assert "Precedence" in result.output
    assert "explicit flag" in result.output
    assert "strict" in result.output
    assert "permissive" in result.output
