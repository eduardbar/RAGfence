"""Shared pytest fixtures: PostgreSQL probe and the ``db`` marker (task 4.6).

DB-gated integration tests (marked ``@pytest.mark.db``) request the
``postgres_dsn`` fixture; when PostgreSQL is unreachable the fixture skips the
test with a clear reason. Unit tests never touch the probe and always run.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

_DEFAULT_TEST_DSN = "postgresql+psycopg://ragfence:ragfence@localhost:5432/ragfence"


def _resolve_dsn() -> str:
    return os.environ.get("RAGFENCE_TEST_DATABASE_DSN") or os.environ.get(
        "RAGFENCE_DATABASE_DSN", _DEFAULT_TEST_DSN
    )


def _postgres_reachable(dsn: str) -> bool:
    try:
        engine = create_engine(dsn, connect_args={"connect_timeout": 1})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "db: PostgreSQL integration test; skipped when no database is reachable.",
    )


@pytest.fixture(scope="session")
def postgres_dsn() -> str:
    """Resolved test DSN; skips the requesting test when PostgreSQL is unreachable."""
    dsn = _resolve_dsn()
    if not _postgres_reachable(dsn):
        pytest.skip("PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN")
    return dsn
