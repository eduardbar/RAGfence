"""CLI stub tests (task 1.3).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- CLI Stub / Scenario: Help exit code — `ragfence --help` exits 0 and prints usage.
"""

import shutil
import subprocess
import sys
from pathlib import Path

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
