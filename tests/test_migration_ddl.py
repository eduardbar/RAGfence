"""Alembic chain verification (task 4.2, no DB).

Runs ``alembic upgrade head --sql`` (offline) and asserts the rendered DDL so
the migration chain is verified without PostgreSQL: 0001 base, 0002 enum types
(CREATE TYPE x5), 0003 tables (vector(1536)), 0004 indexes (HNSW + GIN x2).
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TABLES = {
    "tenants",
    "users",
    "departments",
    "groups",
    "user_groups",
    "documents",
    "document_acl",
    "document_chunks",
    "evaluation_suites",
    "evaluation_cases",
    "evaluation_runs",
    "evaluation_results",
    "security_findings",
}
ENUM_NAMES = (
    "classification",
    "document_status",
    "finding_severity",
    "run_status",
    "scenario_outcome",
)


def _config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    return cfg


def _offline_ddl() -> str:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(_config(), "head", sql=True)
    return buffer.getvalue().lower()


def test_chain_is_single_linear_path_to_head_0004() -> None:
    heads = ScriptDirectory.from_config(_config()).get_heads()
    assert heads == ["0004"]
    script_dir = ScriptDirectory.from_config(_config())
    revisions = [revision.revision for revision in script_dir.walk_revisions()]
    assert revisions == ["0004", "0003", "0002", "0001"]


def test_offline_ddl_creates_all_five_enum_types() -> None:
    ddl = _offline_ddl()
    for enum_name in ENUM_NAMES:
        assert f"create type {enum_name}" in ddl, enum_name


def test_offline_ddl_creates_all_thirteen_tables() -> None:
    ddl = _offline_ddl()
    for table in EXPECTED_TABLES:
        assert f"create table {table}" in ddl, table


def test_offline_ddl_has_vector_hnsw_and_gin_indexes() -> None:
    ddl = _offline_ddl()
    assert "vector(1536)" in ddl
    assert "using hnsw" in ddl
    assert "vector_cosine_ops" in ddl
    assert ddl.count("using gin") == 2


def test_offline_ddl_is_idempotent_structure() -> None:
    """Rendering the chain twice must not change the DDL (deterministic chain)."""
    assert _offline_ddl() == _offline_ddl()
