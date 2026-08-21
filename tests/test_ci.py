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


def test_ci_start_pgvector_service_container() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "pgvector/pgvector" in content
    assert "services:" in content


def test_ci_exports_database_dsn() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "RAGFENCE_TEST_DATABASE_DSN" in content
    assert "postgresql+psycopg://ragfence:ragfence@" in content


def test_ci_runs_migrations_before_tests() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "alembic upgrade head" in content


def test_ci_seeds_reference_database() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "seed_reference_corp" in content


def test_ci_does_not_exclude_integration_tests() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "--ignore=tests/integration" not in content
    assert "--ignore tests/integration" not in content


def test_ci_gates_have_no_continue_on_error() -> None:
    content = CI.read_text(encoding="utf-8")
    assert "continue-on-error" not in content
