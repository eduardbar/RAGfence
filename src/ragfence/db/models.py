"""ORM models for the RAGFence storage schema (docs/BACKEND_SCHEMA.md).

Maps all 13 tables 1:1 with the schema document. Enum columns reference native
Postgres enum types via ``postgresql.ENUM(..., create_type=False)``; DDL for
those types lives in migration 0002. ``create_all`` is forbidden — Alembic owns
all DDL (0003 tables, 0004 indexes). ``documents.deleted_at`` is the soft-delete
marker; repositories filter ``deleted_at IS NULL`` on every read.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ragfence.core.enums import (
    Classification,
    DocumentStatus,
    FindingSeverity,
    ScenarioOutcome,
)
from ragfence.db.base import Base


class RunStatus(StrEnum):
    """Evaluation run lifecycle status (BACKEND_SCHEMA §2)."""

    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    CRASHED = "crashed"


def _enum_values(enum_cls: type[StrEnum]) -> list[str]:
    """Map a Python enum class to its member VALUES for native Postgres enums.

    Migration 0002 creates native enum labels in lowercase (``'public'``,
    ``'running'``, ...). Without ``values_callable`` SQLAlchemy would persist
    member NAMES (uppercase), which PostgreSQL enum comparisons reject and the
    ACL rank CASE could never match (review finding R4-001).
    """

    return [member.value for member in enum_cls]


class Tenant(Base):
    """Isolation boundary #1: every tenant-scoped row belongs to one tenant."""

    __tablename__ = "tenants"
    __table_args__ = (UniqueConstraint("slug", name="uq_tenants_slug"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    users = relationship("User", back_populates="tenant")
    departments = relationship("Department", back_populates="tenant")
    groups = relationship("Group", back_populates="tenant")
    documents = relationship("Document", back_populates="tenant")
    acls = relationship("DocumentACL", back_populates="tenant")
    chunks = relationship("DocumentChunk", back_populates="tenant")


class Department(Base):
    """Organization unit within a tenant (isolation boundary #2)."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_departments_tenant_id_slug"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    tenant = relationship("Tenant", back_populates="departments")
    users = relationship("User", back_populates="department")
    documents = relationship("Document", back_populates="department")
    acls = relationship("DocumentACL", back_populates="department")


class Group(Base):
    """Named group of users; ACL grants can reference group ids."""

    __tablename__ = "groups"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_groups_tenant_id_slug"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    tenant = relationship("Tenant", back_populates="groups")
    users = relationship("UserGroup", back_populates="group")


class User(Base):
    """Authenticated principal; ``classification`` is the max clearance level."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        Index("ix_users_department_id", "department_id"),
        Index("ix_users_tenant_active", "tenant_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[Classification] = mapped_column(
        postgresql.ENUM(
            Classification,
            name="classification",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        server_default="internal",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    tenant = relationship("Tenant", back_populates="users")
    department = relationship("Department", back_populates="users")
    groups = relationship("UserGroup", back_populates="user")


class UserGroup(Base):
    """Join table: users N─M groups (BACKEND_SCHEMA §7)."""

    __tablename__ = "user_groups"
    __table_args__ = (Index("ix_user_groups_group_id", "group_id"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    user = relationship("User", back_populates="groups")
    group = relationship("Group", back_populates="users")


class Document(Base):
    """An ingested document; ``deleted_at`` is the soft-delete marker."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "checksum", name="uq_documents_tenant_id_checksum"),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
        Index("ix_documents_department_id", "department_id"),
        Index("ix_documents_active", "deleted_at", postgresql_where=text("deleted_at IS NULL")),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[Classification] = mapped_column(
        postgresql.ENUM(
            Classification,
            name="classification",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        server_default="internal",
    )
    status: Mapped[DocumentStatus] = mapped_column(
        postgresql.ENUM(
            DocumentStatus,
            name="document_status",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        server_default="pending",
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    tenant = relationship("Tenant", back_populates="documents")
    department = relationship("Department", back_populates="documents")
    acl = relationship("DocumentACL", back_populates="document", uselist=False)
    chunks = relationship("DocumentChunk", back_populates="document")


class DocumentACL(Base):
    """Per-document access rules (1:1 with documents); normalized, typed columns only."""

    __tablename__ = "document_acl"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_document_acl_document_id"),
        Index("ix_document_acl_tenant_classification", "tenant_id", "classification"),
        Index(
            "ix_document_acl_allowed_user_ids_gin",
            "allowed_user_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_document_acl_allowed_group_ids_gin",
            "allowed_group_ids",
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    classification: Mapped[Classification] = mapped_column(
        postgresql.ENUM(
            Classification,
            name="classification",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        server_default="internal",
    )
    allowed_user_ids: Mapped[list[UUID]] = mapped_column(
        postgresql.ARRAY(Uuid),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    allowed_group_ids: Mapped[list[UUID]] = mapped_column(
        postgresql.ARRAY(Uuid),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    document = relationship("Document", back_populates="acl")
    tenant = relationship("Tenant", back_populates="acls")
    department = relationship("Department", back_populates="acls")


class DocumentChunk(Base):
    """A chunk of an ingested document; ``embedding`` is pgvector ``vector(1536)``.

    ``metadata`` (JSONB) carries chunker-specific extras and is NEVER consulted
    by the access predicate (BACKEND_SCHEMA §10.1) — access uses the typed
    columns on ``document_acl`` only.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
        Index("ix_document_chunks_tenant_id", "tenant_id"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        postgresql.JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    document = relationship("Document", back_populates="chunks")
    tenant = relationship("Tenant", back_populates="chunks")


class EvaluationSuite(Base):
    """A named evaluation configuration (e.g. ``default``, ``ci-gate``)."""

    __tablename__ = "evaluation_suites"

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_adapter: Mapped[str] = mapped_column(Text, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("80"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    cases = relationship("EvaluationCase", back_populates="suite")
    runs = relationship("EvaluationRun", back_populates="suite")


class EvaluationCase(Base):
    """A concrete adversarial case; ``actor`` is a JSONB ctx snapshot."""

    __tablename__ = "evaluation_cases"
    __table_args__ = (Index("ix_evaluation_cases_suite_scenario", "suite_id", "scenario_id"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    suite_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_suites.id"), nullable=False)
    scenario_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[dict[str, Any]] = mapped_column(postgresql.JSONB, nullable=False)
    expected_allow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    suite = relationship("EvaluationSuite", back_populates="cases")


class EvaluationRun(Base):
    """A suite execution; carries status, score, and overall outcome."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (Index("ix_evaluation_runs_suite_started", "suite_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    suite_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_suites.id"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        postgresql.ENUM(
            RunStatus,
            name="run_status",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
        server_default="running",
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("80"))
    result: Mapped[ScenarioOutcome | None] = mapped_column(
        postgresql.ENUM(
            ScenarioOutcome,
            name="scenario_outcome",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    suite = relationship("EvaluationSuite", back_populates="runs")
    results = relationship("EvaluationResult", back_populates="run")
    findings = relationship("SecurityFinding", back_populates="run")


class EvaluationResult(Base):
    """Per-case verdict inside a run, with the chunk ids returned as evidence."""

    __tablename__ = "evaluation_results"
    __table_args__ = (
        Index("ix_evaluation_results_run_case", "run_id", "case_id"),
        Index("ix_evaluation_results_run_passed", "run_id", "passed"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_runs.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_cases.id"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[ScenarioOutcome] = mapped_column(
        postgresql.ENUM(
            ScenarioOutcome,
            name="scenario_outcome",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    retrieved_chunk_ids: Mapped[list[UUID]] = mapped_column(
        postgresql.ARRAY(Uuid),
        nullable=False,
        default=list,
        server_default=text("'{}'"),
    )
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    run = relationship("EvaluationRun", back_populates="results")
    case = relationship("EvaluationCase")
    findings = relationship("SecurityFinding", back_populates="result")


class SecurityFinding(Base):
    """Structured security finding; nullable result/case when not case-bound."""

    __tablename__ = "security_findings"
    __table_args__ = (
        Index("ix_security_findings_run_severity", "run_id", "severity"),
        Index("ix_security_findings_category", "category"),
        Index("ix_security_findings_case_id", "case_id"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid, primary_key=True, server_default=text("gen_random_uuid()")
    )
    result_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evaluation_results.id"), nullable=True
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("evaluation_runs.id"), nullable=False)
    case_id: Mapped[UUID | None] = mapped_column(ForeignKey("evaluation_cases.id"), nullable=True)
    severity: Mapped[FindingSeverity] = mapped_column(
        postgresql.ENUM(
            FindingSeverity,
            name="finding_severity",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB, nullable=False, default=dict, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    run = relationship("EvaluationRun", back_populates="findings")
    result = relationship("EvaluationResult", back_populates="findings")
    case = relationship("EvaluationCase")
