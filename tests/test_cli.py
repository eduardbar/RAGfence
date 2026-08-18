"""CLI stub tests (task 1.3).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- CLI Stub / Scenario: Help exit code — `ragfence --help` exits 0 and prints usage.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ragfence.cli.main import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_help_prints_usage() -> None:
    result = runner.invoke(app, ["--help"])
    assert "Usage" in result.output
    assert "ragfence" in result.output


def test_help_lists_phase_six_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("init", "test", "demo", "adapter"):
        assert command in result.output


def test_adapter_check_help_lists_target_options() -> None:
    result = runner.invoke(app, ["adapter", "check", "--help"])
    assert result.exit_code == 0
    assert "base-url" in result.output
    assert "adapter" in result.output


@pytest.mark.parametrize(
    "target_option", [["--adapter", "generic_http"], ["--base-url", "http://target.example"]]
)
def test_test_command_rejects_external_target_with_exit_code_two(
    tmp_path: Path, target_option: list[str]
) -> None:
    config = tmp_path / "ragfence.toml"
    config.write_text('threshold = 0.8\nadapter = "reference"\n', encoding="utf-8")

    result = runner.invoke(app, ["test", "--config", str(config), *target_option])

    assert result.exit_code == 2
    assert "external adapter target is unavailable" in result.output


def _console_script() -> Path:
    """Locate the installed `ragfence` console script for this interpreter."""
    prefix = Path(sys.prefix)
    candidate = (
        prefix / "Scripts" / "ragfence.exe"
        if sys.platform == "win32"
        else prefix / "bin" / "ragfence"
    )
    return candidate if candidate.is_file() else Path(shutil.which("ragfence") or "")


def test_installed_entry_point_help_exits_zero() -> None:
    """Spec scenario end-to-end: GIVEN the package installed, WHEN `ragfence --help` runs."""
    script = _console_script()
    assert script.is_file(), f"console script not found: {script}"
    result = subprocess.run([str(script), "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Usage" in result.stdout
