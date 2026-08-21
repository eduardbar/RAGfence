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


def test_init_up_bootstraps_reference_environment(tmp_path: Path, monkeypatch) -> None:
    called: list[Path] = []
    monkeypatch.setattr(main, "bootstrap_reference", lambda path: called.append(path))

    result = runner.invoke(app, ["init", "--path", str(tmp_path), "--up"])

    assert result.exit_code == 0
    assert called == [tmp_path]


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


def test_test_command_writes_requested_output_path(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "ragfence.toml"
    destination = tmp_path / "evidence" / "report.json"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    monkeypatch.setattr(
        main, "evaluate", lambda *_args, **_kwargs: EvaluationReport(0.9, 0.8, "PASS", [])
    )

    result = runner.invoke(
        app, ["test", "--config", str(config), "--json", "--output", str(destination)]
    )

    assert result.exit_code == 0
    assert destination.is_file()


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


def test_write_report_infers_json_from_json_suffix(tmp_path: Path) -> None:
    """--output con extensión .json escribe JSON aunque no se pase --json."""
    destination = tmp_path / "reports" / "production.json"

    written = write_report(_report(), destination, json_output=False)

    assert written == destination
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["outcome"] == "FAIL"


def test_test_command_output_json_suffix_writes_parseable_report(
    tmp_path: Path, monkeypatch
) -> None:
    """`ragfence test --output report.json` produce un reporte JSON parseable."""
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    monkeypatch.setattr(
        main,
        "evaluate",
        lambda *_args, **_kwargs: EvaluationReport(1.0, 0.8, "pass", []),
    )
    destination = tmp_path / "reports" / "production.json"

    result = runner.invoke(app, ["test", "--config", str(config), "--output", str(destination)])

    assert result.exit_code == 0
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["outcome"] == "pass"


def test_test_command_unwritable_output_fails_closed_with_actionable_error(
    tmp_path: Path, monkeypatch
) -> None:
    """Un destino no escribible produce exit 2 con mensaje accionable, sin traceback."""
    config = tmp_path / "ragfence.toml"
    config.write_text("threshold = 0.8\n", encoding="utf-8")
    monkeypatch.setattr(
        main,
        "evaluate",
        lambda *_args, **_kwargs: EvaluationReport(1.0, 0.8, "pass", []),
    )
    blocker = tmp_path / "blocker.txt"
    blocker.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(
        app, ["test", "--config", str(config), "--output", str(blocker / "report.json")]
    )

    assert result.exit_code == 2
    assert "cannot write report" in result.output
    assert "Traceback" not in result.output


def test_test_command_explicit_missing_config_fails_closed(tmp_path: Path) -> None:
    """Un --config explícito inexistente es error accionable, no defaults silenciosos."""
    result = runner.invoke(app, ["test", "--config", str(tmp_path / "no-existe.toml")])

    assert result.exit_code == 2
    assert "configuration not found" in result.output


def test_bootstrap_skips_compose_when_database_already_reachable(
    tmp_path: Path, monkeypatch
) -> None:
    """init --up es idempotente: si la DSN ya responde, no invoca docker compose."""
    calls: dict[str, object] = {"compose": 0, "migrated": False}

    class _FakeConnection:
        def execute(self, *_args):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _FakeEngine:
        connect_args: dict = {}

        def connect(self):
            return _FakeConnection()

        def dispose(self):
            return None

    monkeypatch.setattr(main, "_reference_root", lambda: tmp_path)
    monkeypatch.setattr(main, "create_engine", lambda *_a, **_k: _FakeEngine())

    class _FakeAlembicConfig:
        def __init__(self, *_args):
            pass

        def set_main_option(self, *_args):
            return None

    monkeypatch.setattr(main, "Config", _FakeAlembicConfig)

    def _fake_upgrade(*_args):
        calls["migrated"] = True

    monkeypatch.setattr(main, "command", type("C", (), {"upgrade": staticmethod(_fake_upgrade)}))

    def _fake_run(*_args, **_kwargs):
        calls["compose"] = calls["compose"] + 1

    monkeypatch.setattr(
        main,
        "subprocess",
        type("S", (), {"run": staticmethod(_fake_run)}),
    )

    seeded: list = []
    monkeypatch.setattr(
        main,
        "Session",
        lambda engine: type(
            "Sess",
            (),
            {"__enter__": lambda s: seeded.append(1) or s, "__exit__": lambda s, *a: False},
        )(),
    )
    monkeypatch.setattr(main, "seed_reference_corp", lambda session: None)

    main.bootstrap_reference(tmp_path)

    assert calls["compose"] == 0, "compose up no debe ejecutarse con la DB ya accesible"
    assert calls["migrated"] is True
