"""DB-gating mechanics (task 4.6, runs without Docker).

Verifies that ``@pytest.mark.db`` is registered and that a DB-marked test is
skipped with the documented reason when PostgreSQL is unreachable.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
# Port 1 on loopback refuses connections immediately: a provably unreachable DSN.
UNREACHABLE_DSN = "postgresql+psycopg://ragfence:ragfence@127.0.0.1:1/ragfence"


def test_db_marker_is_registered(pytestconfig: pytest.Config) -> None:
    registered = {str(marker).split(":")[0].strip() for marker in pytestconfig.getini("markers")}
    assert "db" in registered


def test_db_marked_test_skips_when_postgres_unreachable() -> None:
    probe = REPO_ROOT / "tests" / "_tmp_db_probe_skip.py"
    probe.write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.db\n"
        "def test_requires_postgres(postgres_dsn: str) -> None:\n"
        "    assert postgres_dsn\n"
        "\n",
        encoding="utf-8",
    )
    try:
        env = dict(os.environ)
        env["RAGFENCE_TEST_DATABASE_DSN"] = UNREACHABLE_DSN
        env.pop("RAGFENCE_DATABASE_DSN", None)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe.relative_to(REPO_ROOT)), "-q", "-rs"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    finally:
        probe.unlink(missing_ok=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 skipped" in result.stdout
    assert "PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN" in result.stdout
