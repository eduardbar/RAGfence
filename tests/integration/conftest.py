"""DB-gated integration fixtures (task 4.3).

Every fixture cascades from ``postgres_dsn`` (tests/conftest.py), so all tests
in this package are skipped with a clear reason when PostgreSQL is unreachable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config(dsn: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", dsn)
    return cfg


@pytest.fixture(scope="session")
def migrated_schema(postgres_dsn: str) -> str:
    """Upgrade the test database to head; repeat runs are idempotent no-ops."""
    command.upgrade(_alembic_config(postgres_dsn), "head")
    return postgres_dsn


@pytest.fixture(scope="session")
def db_engine(migrated_schema: str):
    """SQLAlchemy engine bound to the migrated test database."""
    engine = create_engine(migrated_schema)
    yield engine
    engine.dispose()
