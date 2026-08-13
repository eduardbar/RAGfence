"""DB-gated storage-schema integration tests (task 4.3).

Skipped with ``PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN`` when no
database is reachable. Spec reference:
openspec/changes/ragfence-foundation/specs/storage-schema/spec.md
- Alembic Migration Chain / Scenario: Fresh and repeat migration
- Vector and Index Defaults / Scenario: Indexes present after upgrade
- Soft Delete Semantics / Scenario: Deleted rows excluded
- Repositories / Scenario: Tenant isolation
- Normalized ACL vs JSONB Metadata / Scenario: Metadata spoofing has no effect
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import and_, create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.core.models import AuthorizationContext
from ragfence.db.models import Document, DocumentACL, Tenant
from ragfence.db.repositories import DocumentRepository, build_acl_predicate

REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _alembic_config(dsn: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", dsn)
    return cfg


def _checksum() -> str:
    return hashlib.sha256(uuid4().bytes).hexdigest()


@pytest.mark.db
def test_upgrade_head_twice_is_a_noop(migrated_schema: str) -> None:
    cfg = _alembic_config(migrated_schema)
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    finally:
        engine.dispose()
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert version == heads[0]


@pytest.mark.db
def test_upgrade_creates_all_tables_and_enum_types(migrated_schema: str) -> None:
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            enums = {
                row[0]
                for row in conn.execute(text("SELECT typname FROM pg_type WHERE typtype = 'e'"))
            }
    finally:
        engine.dispose()
    assert EXPECTED_TABLES <= tables
    assert set(ENUM_NAMES) <= enums


@pytest.mark.db
def test_hnsw_and_gin_indexes_present(migrated_schema: str) -> None:
    engine = create_engine(migrated_schema)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'")
            ).all()
    finally:
        engine.dispose()
    indexdefs = {name: definition for name, definition in rows}
    assert "using hnsw" in indexdefs["ix_document_chunks_embedding_hnsw"].lower()
    assert "vector_cosine_ops" in indexdefs["ix_document_chunks_embedding_hnsw"].lower()
    assert "using gin" in indexdefs["ix_document_acl_allowed_user_ids_gin"].lower()
    assert "using gin" in indexdefs["ix_document_acl_allowed_group_ids_gin"].lower()


@pytest.mark.db
def test_soft_deleted_document_is_excluded_from_repository(db_engine: Engine) -> None:
    tenant = Tenant(name="SoftDelete Co", slug=f"soft-{uuid4().hex[:8]}")
    document = Document(
        tenant=tenant,
        title="Sensitive Payroll",
        source="acme-synthetic",
        checksum=_checksum(),
        classification=Classification.CONFIDENTIAL,
        status=DocumentStatus.READY,
    )
    with Session(db_engine) as session:
        session.add(document)
        session.commit()
        document_id = document.id
        repo = DocumentRepository(session, tenant_id=tenant.id)
        assert document_id in {row.id for row in repo.list_active()}
        document.deleted_at = datetime.now(UTC)
        session.commit()
        assert document_id not in {row.id for row in repo.list_active()}
        # the row remains in storage for audit
        remaining = session.get(Document, document_id)
        assert remaining is not None
        assert remaining.deleted_at is not None


@pytest.mark.db
def test_tenant_isolation_between_repositories(db_engine: Engine) -> None:
    tenant_a = Tenant(name="Tenant A", slug=f"tenant-a-{uuid4().hex[:8]}")
    tenant_b = Tenant(name="Tenant B", slug=f"tenant-b-{uuid4().hex[:8]}")
    doc_a = Document(
        tenant=tenant_a,
        title="A-only document",
        source="acme-synthetic",
        checksum=_checksum(),
        status=DocumentStatus.READY,
    )
    doc_b = Document(
        tenant=tenant_b,
        title="B-only document",
        source="acme-synthetic",
        checksum=_checksum(),
        status=DocumentStatus.READY,
    )
    with Session(db_engine) as session:
        session.add_all([doc_a, doc_b])
        session.commit()
        repo_a = DocumentRepository(session, tenant_id=tenant_a.id)
        repo_b = DocumentRepository(session, tenant_id=tenant_b.id)
        ids_a = {row.id for row in repo_a.list_active()}
        ids_b = {row.id for row in repo_b.list_active()}
    assert doc_a.id in ids_a
    assert doc_b.id not in ids_a
    assert doc_b.id in ids_b
    assert doc_a.id not in ids_b


@pytest.mark.db
def test_jsonb_metadata_spoofing_does_not_change_access_decision(db_engine: Engine) -> None:
    """Chunk metadata that spoofs another tenant never alters the ACL predicate."""
    tenant_a = Tenant(name="Spoof A", slug=f"spoof-a-{uuid4().hex[:8]}")
    tenant_b = Tenant(name="Spoof B", slug=f"spoof-b-{uuid4().hex[:8]}")
    with Session(db_engine) as session:
        session.add_all([tenant_a, tenant_b])
        session.commit()
        tenant_a_id, tenant_b_id = tenant_a.id, tenant_b.id
        conn = db_engine.connect()
        try:
            doc_id = conn.execute(
                text(
                    "INSERT INTO documents "
                    "(tenant_id, title, source, checksum, classification, status) "
                    "VALUES (:tenant_id, 'CFO Payroll Summary', 'acme-synthetic', "
                    ":checksum, 'confidential', 'ready') "
                    "RETURNING id"
                ),
                {"tenant_id": tenant_a_id, "checksum": _checksum()},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO document_acl (document_id, tenant_id, classification) "
                    "VALUES (:document_id, :tenant_id, 'confidential')"
                ),
                {"document_id": doc_id, "tenant_id": tenant_a_id},
            )
            conn.execute(
                text(
                    "INSERT INTO document_chunks "
                    "(document_id, tenant_id, chunk_index, content, metadata) "
                    "VALUES (:document_id, :tenant_id, 0, 'leaked payload', '{}'::jsonb)"
                ),
                {"document_id": doc_id, "tenant_id": tenant_a_id},
            )
            conn.commit()
        finally:
            conn.close()

    ctx = AuthorizationContext(
        tenant_id=tenant_b_id,  # attacker from the OTHER tenant
        user_id=uuid4(),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )
    predicate = build_acl_predicate(DocumentACL, ctx)

    def _decision() -> bool:
        stmt = (
            select(DocumentACL.document_id)
            .where(and_(predicate, DocumentACL.document_id == doc_id))
            .limit(1)
        )
        with db_engine.connect() as conn:
            return conn.execute(stmt).scalar_one_or_none() is not None

    assert _decision() is False  # cross-tenant document is denied
    # Spoof the chunk JSONB metadata to look like it belongs to the attacker's tenant.
    with db_engine.connect() as conn:
        conn.execute(
            text(
                "UPDATE document_chunks SET metadata = jsonb_build_object('tenant_id', :spoofed) "
                "WHERE document_id = :document_id"
            ),
            {"spoofed": str(tenant_b_id), "document_id": doc_id},
        )
        conn.commit()
    # The predicate references typed columns only: the decision is unchanged.
    assert _decision() is False
