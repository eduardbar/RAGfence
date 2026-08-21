"""CLI integration contracts for the generic HTTP adapter."""

import json
from pathlib import Path

from typer.testing import CliRunner

from ragfence.cli.main import app

runner = CliRunner()


def _config(path: Path, *, base_url: str = "http://stub", token: str | None = None) -> None:
    auth = f'auth_token = "{token}"\n' if token else ""
    path.write_text(
        'threshold = 0.0\nadapter = "generic_http"\n\n'
        "[adapters.generic_http]\n"
        f'base_url = "{base_url}"\nretrieve_path = "retrieve"\nhealth_path = "health"\n{auth}',
        encoding="utf-8",
    )


def test_adapter_check_generic_http_valid_reports_available(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    _config(config)
    monkeypatch.setattr("ragfence.cli.seams.create_adapter", lambda name, cfg: _HealthyAdapter())

    result = runner.invoke(app, ["adapter", "check", "generic_http", "--config", str(config)])

    assert result.exit_code == 0
    assert "adapter available: generic_http" in result.output
    assert "Bearer" not in result.output


def test_adapter_check_generic_http_unhealthy_exits_two(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    _config(config)
    monkeypatch.setattr("ragfence.cli.seams.create_adapter", lambda name, cfg: _UnhealthyAdapter())

    result = runner.invoke(app, ["adapter", "check", "generic_http", "--config", str(config)])

    assert result.exit_code == 2
    assert "unhealthy" in result.output.lower()


def test_adapter_check_generic_http_invalid_config_is_safe(tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text(
        'adapter = "generic_http"\n[adapters.generic_http]\nbase_url = "not-a-url"\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["adapter", "check", "generic_http", "--config", str(config)])

    assert result.exit_code == 2
    assert "not-a-url" not in result.output
    assert "invalid adapters.generic_http configuration" in result.output


def test_test_generic_http_invokes_adapter_writes_redacted_report_and_threshold(
    monkeypatch, tmp_path: Path
) -> None:
    config = tmp_path / "ragfence.toml"
    _config(config, token="super-secret-token")
    target = _HealthyAdapter(answer_text="blocked response " + "x" * 1000)
    monkeypatch.setattr("ragfence.cli.seams.create_adapter", lambda name, cfg: target)

    result = runner.invoke(
        app,
        ["test", "--config", str(config), "--adapter", "generic_http", "--json"],
    )

    assert result.exit_code in {0, 1}
    report_path = tmp_path / ".ragfence" / "reports" / "latest.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    encoded = json.dumps(report)
    assert target.retrieve_calls > 0
    assert len(encoded) < 10000
    assert "super-secret-token" not in encoded
    assert "Bearer" not in encoded


class _HealthyAdapter:
    name = "generic_http"

    def __init__(self, *, answer_text: str = "blocked") -> None:
        self.retrieve_calls = 0
        self.answer_text = answer_text

    def is_healthy(self) -> bool:
        return True

    def retrieve(self, request):
        self.retrieve_calls += 1
        return []

    def answer(self, request, chunks):
        return self.answer_text

    def check_identity_represented(self) -> bool:
        return True


class _UnhealthyAdapter(_HealthyAdapter):
    def is_healthy(self) -> bool:
        return False
