"""tables: create the 13 storage-schema tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PK_UUID = sa.Uuid()
TS = sa.TIMESTAMP(timezone=True)
CLS = postgresql.ENUM("public", "internal", "confidential", "restricted", name="classification", create_type=False)
DOC_STATUS = postgresql.ENUM("pending", "ready", "failed", name="document_status", create_type=False)
FINDING_SEV = postgresql.ENUM("low", "medium", "high", "critical", name="finding_severity", create_type=False)
RUN_STATUS = postgresql.ENUM("running", "passed", "failed", "crashed", name="run_status", create_type=False)
SCENARIO_OUTCOME = postgresql.ENUM("pass", "warning", "fail", "critical", name="scenario_outcome", create_type=False)
UUID_ARRAY = postgresql.ARRAY(sa.Uuid())


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_table(
        "departments",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_departments_tenant_id_slug"),
    )
    op.create_table(
        "groups",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_groups_tenant_id_slug"),
    )
    op.create_table(
        "users",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("classification", CLS, nullable=False, server_default="internal"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
    )
    op.create_table(
        "user_groups",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("group_id", sa.Uuid(), sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "documents",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("classification", CLS, nullable=False, server_default="internal"),
        sa.Column("status", DOC_STATUS, nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", TS, nullable=True),
        sa.UniqueConstraint("tenant_id", "checksum", name="uq_documents_tenant_id_checksum"),
    )
    op.create_table(
        "document_acl",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("department_id", sa.Uuid(), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("classification", CLS, nullable=False, server_default="internal"),
        sa.Column("allowed_user_ids", UUID_ARRAY, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("allowed_group_ids", UUID_ARRAY, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", name="uq_document_acl_document_id"),
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
    )
    op.create_table(
        "evaluation_suites",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_adapter", sa.Text(), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default=sa.text("80")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "evaluation_cases",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("suite_id", sa.Uuid(), sa.ForeignKey("evaluation_suites.id"), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("actor", postgresql.JSONB(), nullable=False),
        sa.Column("expected_allow", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "evaluation_runs",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("suite_id", sa.Uuid(), sa.ForeignKey("evaluation_suites.id"), nullable=False),
        sa.Column("status", RUN_STATUS, nullable=False, server_default="running"),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default=sa.text("80")),
        sa.Column("result", SCENARIO_OUTCOME, nullable=True),
        sa.Column("started_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", TS, nullable=True),
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("evaluation_cases.id"), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("outcome", SCENARIO_OUTCOME, nullable=False),
        sa.Column("retrieved_chunk_ids", UUID_ARRAY, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "security_findings",
        sa.Column("id", PK_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("result_id", sa.Uuid(), sa.ForeignKey("evaluation_results.id"), nullable=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("evaluation_runs.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("evaluation_cases.id"), nullable=True),
        sa.Column("severity", FINDING_SEV, nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("security_findings")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_suites")
    op.drop_table("document_chunks")
    op.drop_table("document_acl")
    op.drop_table("documents")
    op.drop_table("user_groups")
    op.drop_table("users")
    op.drop_table("groups")
    op.drop_table("departments")
    op.drop_table("tenants")
