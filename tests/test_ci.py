"""CI workflow validation (task 1.5).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- Continuous Integration / Scenario: CI matrix — Python 3.12; every gate must pass.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"

GATES = ("ruff check", "ruff format --check", "mypy", "python -m pytest")


def test_workflow_runs_on_push_and_pr() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "push" in content
    assert "pull_request" in content


def test_matrix_pins_python_312() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "3.12" in content


def test_all_gates_present() -> None:
    content = CI.read_text(encoding="utf-8")
    for gate in GATES:
        assert gate in content
