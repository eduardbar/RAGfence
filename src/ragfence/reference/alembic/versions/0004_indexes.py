"""indexes: HNSW vector index, GIN ACL indexes, and the schema's btree indexes.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # HNSW approximate nearest-neighbor index over the pgvector column.
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    # GIN indexes let the ACL predicate filter on allowlist membership.
    op.create_index(
        "ix_document_acl_allowed_user_ids_gin",
        "document_acl",
        ["allowed_user_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_acl_allowed_group_ids_gin",
        "document_acl",
        ["allowed_group_ids"],
        postgresql_using="gin",
    )
    # Remaining btree indexes from BACKEND_SCHEMA (per-table index lists).
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.create_index("ix_users_tenant_active", "users", ["tenant_id", "is_active"])
    op.create_index("ix_user_groups_group_id", "user_groups", ["group_id"])
    op.create_index("ix_documents_tenant_status", "documents", ["tenant_id", "status"])
    op.create_index("ix_documents_department_id", "documents", ["department_id"])
    op.create_index(
        "ix_documents_active",
        "documents",
        ["deleted_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_document_acl_tenant_classification", "document_acl", ["tenant_id", "classification"]
    )
    op.create_index("ix_document_chunks_tenant_id", "document_chunks", ["tenant_id"])
    op.create_index(
        "ix_evaluation_cases_suite_scenario", "evaluation_cases", ["suite_id", "scenario_id"]
    )
    op.create_index(
        "ix_evaluation_runs_suite_started", "evaluation_runs", ["suite_id", "started_at"]
    )
    op.create_index("ix_evaluation_results_run_case", "evaluation_results", ["run_id", "case_id"])
    op.create_index("ix_evaluation_results_run_passed", "evaluation_results", ["run_id", "passed"])
    op.create_index(
        "ix_security_findings_run_severity", "security_findings", ["run_id", "severity"]
    )
    op.create_index("ix_security_findings_category", "security_findings", ["category"])
    op.create_index("ix_security_findings_case_id", "security_findings", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_security_findings_case_id", table_name="security_findings")
    op.drop_index("ix_security_findings_category", table_name="security_findings")
    op.drop_index("ix_security_findings_run_severity", table_name="security_findings")
    op.drop_index("ix_evaluation_results_run_passed", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_run_case", table_name="evaluation_results")
    op.drop_index("ix_evaluation_runs_suite_started", table_name="evaluation_runs")
    op.drop_index("ix_evaluation_cases_suite_scenario", table_name="evaluation_cases")
    op.drop_index("ix_document_chunks_tenant_id", table_name="document_chunks")
    op.drop_index("ix_document_acl_tenant_classification", table_name="document_acl")
    op.drop_index("ix_documents_active", table_name="documents")
    op.drop_index("ix_documents_department_id", table_name="documents")
    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_index("ix_user_groups_group_id", table_name="user_groups")
    op.drop_index("ix_users_tenant_active", table_name="users")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_index("ix_document_acl_allowed_group_ids_gin", table_name="document_acl")
    op.drop_index("ix_document_acl_allowed_user_ids_gin", table_name="document_acl")
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
