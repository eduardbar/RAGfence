"""Release Work Unit 5: clean offline CLI E2E proof."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragfence.cli.main import app

runner = CliRunner()


def test_clean_init_test_report_e2e_uses_no_network_or_real_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh project can initialize, run the deterministic fake/reference suite, and report."""
    original_socket = socket.socket

    class GuardedSocket(original_socket):  # type: ignore[misc]
        def connect(self, address: tuple[str, int] | tuple[str, int, int, int]) -> None:
            if self.family == socket.AF_INET:
                host = address[0]
                if host not in ("127.0.0.1", "localhost", "::1"):
                    raise AssertionError(f"non-loopback connection attempted: {host}")
            super().connect(address)

        def connect_ex(self, address: tuple[str, int] | tuple[str, int, int, int]) -> int:
            if self.family == socket.AF_INET:
                host = address[0]
                if host not in ("127.0.0.1", "localhost", "::1"):
                    raise AssertionError(f"non-loopback connection attempted: {host}")
            return super().connect_ex(address)

    monkeypatch.setattr(socket, "socket", GuardedSocket)

    # R5.1 clean-room flow: init --up starts, migrates, and idempotently seeds the
    # local reference DB so this proof never depends on ambient database state.
    init = runner.invoke(app, ["init", "--path", str(tmp_path), "--up"])
    assert init.exit_code == 0, init.output
    config = tmp_path / "ragfence.toml"
    report_path = tmp_path / ".ragfence" / "reports" / "latest.json"
    assert config.is_file()

    evaluation = runner.invoke(app, ["test", "--config", str(config), "--json"])
    assert evaluation.exit_code == 0, evaluation.output
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["results"]
    assert payload["score"] >= payload["threshold"]
    assert payload["outcome"] == "pass"
    assert payload["real_provider_used"] is False
    rendered = report_path.read_text(encoding="utf-8").lower()
    assert "top-secret" not in rendered
    assert "api_key" not in rendered


def test_clean_e2e_preserves_exit_status_contract(tmp_path: Path) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text('threshold = 0.8\nadapter = "reference"\n', encoding="utf-8")

    rejected = runner.invoke(
        app, ["test", "--config", str(config), "--base-url", "https://example.invalid"]
    )
    assert rejected.exit_code == 2
    assert "external adapter target is unavailable" in rejected.output
