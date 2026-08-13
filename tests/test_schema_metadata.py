"""ORM metadata vs docs/BACKEND_SCHEMA.md (task 4.1, no DB).

Every expectation below is transcribed from docs/BACKEND_SCHEMA.md so that a
change to either the schema doc or the ORM models fails loudly without needing
PostgreSQL. DDL ownership is Alembic-only: ``create_all`` is forbidden, so the
metadata must never emit ``CREATE TYPE`` for the native enum columns.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from ragfence.db import models as db_models  # noqa: F401  (register all tables on Base.metadata)
from ragfence.db.base import Base

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


def _timestamptz(t: Any) -> bool:
    return isinstance(t, DateTime) and t.timezone is True


def _enum_type(name: str) -> Callable[[Any], bool]:
    def _check(t: Any) -> bool:
        return isinstance(t, Enum) and t.name == name and getattr(t, "create_type", True) is False

    return _check


def _uuid_array(t: Any) -> bool:
    return isinstance(t, postgresql.ARRAY) and isinstance(t.item_type, Uuid)


def _jsonb(t: Any) -> bool:
    return isinstance(t, postgresql.JSONB)


def _numeric_5_2(t: Any) -> bool:
    return isinstance(t, Numeric) and t.precision == 5 and t.scale == 2


def _vector_1536(t: Any) -> bool:
    return isinstance(t, Vector) and t.dim == 1536


# table -> column -> (type check, nullable, server-default substring or None)
COLUMN_SHAPES: dict[str, dict[str, tuple[Callable[[Any], bool], bool, str | None]]] = {
    "tenants": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "name": (Text, False, None),
        "slug": (Text, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "users": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "tenant_id": (Uuid, False, None),
        "department_id": (Uuid, True, None),
        "email": (Text, False, None),
        "password_hash": (Text, False, None),
        "display_name": (Text, False, None),
        "classification": (_enum_type("classification"), False, "internal"),
        "is_active": (Boolean, False, "true"),
        "created_at": (_timestamptz, False, "now()"),
        "updated_at": (_timestamptz, False, "now()"),
    },
    "departments": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "tenant_id": (Uuid, False, None),
        "name": (Text, False, None),
        "slug": (Text, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "groups": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "tenant_id": (Uuid, False, None),
        "name": (Text, False, None),
        "slug": (Text, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "user_groups": {
        "user_id": (Uuid, False, None),
        "group_id": (Uuid, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "documents": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "tenant_id": (Uuid, False, None),
        "department_id": (Uuid, True, None),
        "title": (Text, False, None),
        "source": (Text, False, None),
        "checksum": (Text, False, None),
        "classification": (_enum_type("classification"), False, "internal"),
        "status": (_enum_type("document_status"), False, "pending"),
        "version": (Integer, False, "1"),
        "created_at": (_timestamptz, False, "now()"),
        "updated_at": (_timestamptz, False, "now()"),
        "deleted_at": (_timestamptz, True, None),
    },
    "document_acl": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "document_id": (Uuid, False, None),
        "tenant_id": (Uuid, False, None),
        "department_id": (Uuid, True, None),
        "classification": (_enum_type("classification"), False, "internal"),
        "allowed_user_ids": (_uuid_array, False, "'{}'"),
        "allowed_group_ids": (_uuid_array, False, "'{}'"),
        "created_at": (_timestamptz, False, "now()"),
        "updated_at": (_timestamptz, False, "now()"),
    },
    "document_chunks": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "document_id": (Uuid, False, None),
        "tenant_id": (Uuid, False, None),
        "chunk_index": (Integer, False, None),
        "content": (Text, False, None),
        "embedding": (_vector_1536, True, None),
        "metadata": (_jsonb, False, "'{}'"),
        "created_at": (_timestamptz, False, "now()"),
    },
    "evaluation_suites": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "name": (Text, False, None),
        "description": (Text, True, None),
        "target_adapter": (Text, False, None),
        "threshold": (Integer, False, "80"),
        "created_at": (_timestamptz, False, "now()"),
        "updated_at": (_timestamptz, False, "now()"),
    },
    "evaluation_cases": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "suite_id": (Uuid, False, None),
        "scenario_id": (Text, False, None),
        "prompt": (Text, False, None),
        "actor": (_jsonb, False, None),
        "expected_allow": (Boolean, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "evaluation_runs": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "suite_id": (Uuid, False, None),
        "status": (_enum_type("run_status"), False, "running"),
        "score": (_numeric_5_2, True, None),
        "threshold": (Integer, False, "80"),
        "result": (_enum_type("scenario_outcome"), True, None),
        "started_at": (_timestamptz, False, "now()"),
        "finished_at": (_timestamptz, True, None),
    },
    "evaluation_results": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "run_id": (Uuid, False, None),
        "case_id": (Uuid, False, None),
        "passed": (Boolean, False, None),
        "outcome": (_enum_type("scenario_outcome"), False, None),
        "retrieved_chunk_ids": (_uuid_array, False, "'{}'"),
        "answer": (Text, True, None),
        "latency_ms": (Integer, False, None),
        "created_at": (_timestamptz, False, "now()"),
    },
    "security_findings": {
        "id": (Uuid, False, "gen_random_uuid()"),
        "result_id": (Uuid, True, None),
        "run_id": (Uuid, False, None),
        "case_id": (Uuid, True, None),
        "severity": (_enum_type("finding_severity"), False, None),
        "category": (Text, False, None),
        "title": (Text, False, None),
        "description": (Text, False, None),
        "evidence": (_jsonb, False, "'{}'"),
        "created_at": (_timestamptz, False, "now()"),
    },
}

ENUM_COLUMNS = {
    "users.classification": "classification",
    "documents.classification": "classification",
    "documents.status": "document_status",
    "document_acl.classification": "classification",
    "evaluation_runs.status": "run_status",
    "evaluation_runs.result": "scenario_outcome",
    "evaluation_results.outcome": "scenario_outcome",
    "security_findings.severity": "finding_severity",
}

UNIQUE_CONSTRAINTS: dict[str, list[tuple[str, ...]]] = {
    "tenants": [("slug",)],
    "users": [("tenant_id", "email")],
    "departments": [("tenant_id", "slug")],
    "groups": [("tenant_id", "slug")],
    "documents": [("tenant_id", "checksum")],
    "document_acl": [("document_id",)],
    "document_chunks": [("document_id", "chunk_index")],
}

# table -> {relationship name: (target class name, uselist)}
RELATIONSHIPS: dict[str, dict[str, tuple[str, bool]]] = {
    "tenants": {
        "users": ("User", True),
        "departments": ("Department", True),
        "groups": ("Group", True),
        "documents": ("Document", True),
        "acls": ("DocumentACL", True),
        "chunks": ("DocumentChunk", True),
    },
    "users": {
        "tenant": ("Tenant", False),
        "department": ("Department", False),
        "groups": ("UserGroup", True),
    },
    "departments": {
        "tenant": ("Tenant", False),
        "users": ("User", True),
        "documents": ("Document", True),
        "acls": ("DocumentACL", True),
    },
    "groups": {
        "tenant": ("Tenant", False),
        "users": ("UserGroup", True),
    },
    "user_groups": {
        "user": ("User", False),
        "group": ("Group", False),
    },
    "documents": {
        "tenant": ("Tenant", False),
        "department": ("Department", False),
        "acl": ("DocumentACL", False),
        "chunks": ("DocumentChunk", True),
    },
    "document_acl": {
        "document": ("Document", False),
        "tenant": ("Tenant", False),
        "department": ("Department", False),
    },
    "document_chunks": {
        "document": ("Document", False),
        "tenant": ("Tenant", False),
    },
    "evaluation_suites": {
        "cases": ("EvaluationCase", True),
        "runs": ("EvaluationRun", True),
    },
    "evaluation_cases": {
        "suite": ("EvaluationSuite", False),
    },
    "evaluation_runs": {
        "suite": ("EvaluationSuite", False),
        "results": ("EvaluationResult", True),
        "findings": ("SecurityFinding", True),
    },
    "evaluation_results": {
        "run": ("EvaluationRun", False),
        "case": ("EvaluationCase", False),
        "findings": ("SecurityFinding", True),
    },
    "security_findings": {
        "run": ("EvaluationRun", False),
        "result": ("EvaluationResult", False),
        "case": ("EvaluationCase", False),
    },
}

# table -> index names declared in the ORM metadata
EXPECTED_INDEXES: dict[str, set[str]] = {
    "users": {"ix_users_department_id", "ix_users_tenant_active"},
    "user_groups": {"ix_user_groups_group_id"},
    "documents": {
        "ix_documents_tenant_status",
        "ix_documents_department_id",
        "ix_documents_active",
    },
    "document_acl": {
        "ix_document_acl_tenant_classification",
        "ix_document_acl_allowed_user_ids_gin",
        "ix_document_acl_allowed_group_ids_gin",
    },
    "document_chunks": {"ix_document_chunks_tenant_id", "ix_document_chunks_embedding_hnsw"},
    "evaluation_cases": {"ix_evaluation_cases_suite_scenario"},
    "evaluation_runs": {"ix_evaluation_runs_suite_started"},
    "evaluation_results": {"ix_evaluation_results_run_case", "ix_evaluation_results_run_passed"},
    "security_findings": {
        "ix_security_findings_run_severity",
        "ix_security_findings_category",
        "ix_security_findings_case_id",
    },
}


def _default_sql(col: Any) -> str:
    if col.server_default is None:
        return ""
    return str(col.server_default.arg)


def test_metadata_has_exactly_the_13_schema_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_column_shapes_match_schema_doc() -> None:
    assert set(COLUMN_SHAPES) == EXPECTED_TABLES  # the expectations cover every table
    for table_name, columns in COLUMN_SHAPES.items():
        table = Base.metadata.tables[table_name]
        assert set(table.c.keys()) == set(columns), f"{table_name} column names"
        for column_name, (type_check, nullable, default_substr) in columns.items():
            col = table.c[column_name]
            if isinstance(type_check, type):
                assert isinstance(col.type, type_check), f"{table_name}.{column_name} type"
            else:
                assert type_check(col.type), f"{table_name}.{column_name} type"
            assert col.nullable is nullable, f"{table_name}.{column_name} nullable"
            if default_substr is None:
                assert _default_sql(col) == "", f"{table_name}.{column_name} unexpected default"
            else:
                assert default_substr in _default_sql(col), f"{table_name}.{column_name} default"


def test_enum_columns_use_native_postgres_types_without_create() -> None:
    for qualified, enum_name in ENUM_COLUMNS.items():
        table_name, column_name = qualified.split(".")
        col = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(col.type, Enum), qualified
        assert col.type.name == enum_name, qualified
        assert col.type.create_type is False, qualified


def test_acl_arrays_are_uuid_arrays_defaulting_to_empty() -> None:
    for qualified in (
        "document_acl.allowed_user_ids",
        "document_acl.allowed_group_ids",
        "evaluation_results.retrieved_chunk_ids",
    ):
        table_name, column_name = qualified.split(".")
        col = Base.metadata.tables[table_name].c[column_name]
        assert isinstance(col.type, postgresql.ARRAY), qualified
        assert isinstance(col.type.item_type, Uuid), qualified
        assert col.nullable is False, qualified
        assert _default_sql(col) == "'{}'", qualified


def test_documents_deleted_at_is_nullable_timestamptz() -> None:
    col = Base.metadata.tables["documents"].c["deleted_at"]
    assert col.nullable is True
    assert isinstance(col.type, DateTime) and col.type.timezone is True
    # only documents carries a soft-delete marker in the schema
    for table in EXPECTED_TABLES - {"documents"}:
        assert "deleted_at" not in Base.metadata.tables[table].c


def test_user_groups_has_composite_primary_key() -> None:
    table = Base.metadata.tables["user_groups"]
    pk = next(c for c in table.constraints if isinstance(c, PrimaryKeyConstraint))
    assert list(pk.columns) == [table.c["user_id"], table.c["group_id"]]


def test_unique_constraints_match_schema() -> None:
    for table_name, expected in UNIQUE_CONSTRAINTS.items():
        table = Base.metadata.tables[table_name]
        unique_cols = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert unique_cols == set(expected), table_name


def test_foreign_keys_reference_schema_tables() -> None:
    expected_fks = {
        "users": {"tenants", "departments"},
        "departments": {"tenants"},
        "groups": {"tenants"},
        "user_groups": {"users", "groups"},
        "documents": {"tenants", "departments"},
        "document_acl": {"documents", "tenants", "departments"},
        "document_chunks": {"documents", "tenants"},
        "evaluation_cases": {"evaluation_suites"},
        "evaluation_runs": {"evaluation_suites"},
        "evaluation_results": {"evaluation_runs", "evaluation_cases"},
        "security_findings": {"evaluation_results", "evaluation_runs", "evaluation_cases"},
    }
    for table_name, targets in expected_fks.items():
        table = Base.metadata.tables[table_name]
        fk_targets = {fk.column.table.name for fk in table.foreign_keys}
        assert fk_targets == targets, table_name


def test_relationships_match_schema() -> None:
    class_by_table = {
        mapper.local_table.name: mapper.class_
        for mapper in Base.registry.mappers
        if mapper.local_table is not None
    }
    for table_name, expected in RELATIONSHIPS.items():
        mapper = class_by_table[table_name].__mapper__
        actual = {name: rel for name, rel in mapper.relationships.items() if name in expected}
        assert set(actual) == set(expected), table_name
        for name, (target_class, uselist) in expected.items():
            rel = actual[name]
            assert rel.mapper.class_.__name__ == target_class, f"{table_name}.{name} target"
            assert rel.uselist is uselist, f"{table_name}.{name} uselist"


def test_indexes_are_declared_in_metadata() -> None:
    for table_name, expected in EXPECTED_INDEXES.items():
        table = Base.metadata.tables[table_name]
        declared = {index.name for index in table.indexes}
        assert expected <= declared, table_name


def test_hnsw_index_uses_cosine_ops() -> None:
    index = next(
        i
        for i in Base.metadata.tables["document_chunks"].indexes
        if i.name == "ix_document_chunks_embedding_hnsw"
    )
    assert index.dialect_kwargs["postgresql_using"] == "hnsw"
    assert index.dialect_kwargs["postgresql_ops"]["embedding"] == "vector_cosine_ops"


def test_gin_indexes_on_acl_arrays() -> None:
    for name in ("ix_document_acl_allowed_user_ids_gin", "ix_document_acl_allowed_group_ids_gin"):
        index = next(i for i in Base.metadata.tables["document_acl"].indexes if i.name == name)
        assert index.dialect_kwargs["postgresql_using"] == "gin"


def test_documents_active_index_is_partial_on_deleted_at() -> None:
    index = next(
        i for i in Base.metadata.tables["documents"].indexes if i.name == "ix_documents_active"
    )
    assert index.dialect_kwargs["postgresql_where"] is not None


def test_run_status_matches_schema_enum_values() -> None:
    assert [member.value for member in db_models.RunStatus] == [
        "running",
        "passed",
        "failed",
        "crashed",
    ]


def test_metadata_never_emits_create_type_for_enum_columns() -> None:
    """create_all is forbidden: native enum DDL belongs to migration 0002."""
    dialect = postgresql.dialect()
    for table_name in EXPECTED_TABLES:
        ddl = str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=dialect))
        assert "create type" not in ddl.lower(), table_name


NATIVE_ENUM_COLUMNS: dict[str, list[str]] = {
    "users": ["classification"],
    "documents": ["classification", "status"],
    "document_acl": ["classification"],
    "evaluation_runs": ["status", "result"],
    "evaluation_results": ["outcome"],
    "security_findings": ["severity"],
}


def test_enum_columns_persist_lowercase_values_via_values_callable() -> None:
    """Regression (review finding R4-001): native enum labels in migration 0002
    are lowercase ('public', 'running', ...), so every postgresql.ENUM column
    MUST coerce Python enum members to their .value via values_callable.

    Without it, SQLAlchemy persists member NAMES (uppercase 'CONFIDENTIAL',
    'RUNNING'), which PostgreSQL enum comparisons reject and the ACL rank CASE
    can never match. This test pins the coercion contract without a database.
    """
    for table_name, column_names in NATIVE_ENUM_COLUMNS.items():
        table = Base.metadata.tables[table_name]
        for column_name in column_names:
            column = table.c[column_name]
            enum_type = column.type
            assert isinstance(enum_type, Enum), (table_name, column_name)
            assert enum_type.values_callable is not None, (table_name, column_name)
            member_values = [
                member.value for member in enum_type.enum_class  # type: ignore[union-attr]
            ]
            assert all(isinstance(v, str) and v == v.lower() for v in member_values), (
                table_name,
                column_name,
            )
