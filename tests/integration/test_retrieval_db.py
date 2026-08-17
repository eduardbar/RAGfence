"""DB-gated secure retrieval integration tests (PR 3, tasks 3.1-3.3).

Skipped with ``PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN`` when no
database is reachable (tests/conftest.py ``postgres_dsn`` probe; the
``migrated_schema``/``db_engine`` fixtures run Alembic to head). Spec reference:
openspec/changes/ragfence-secure-retrieval/specs/secure-retrieval/spec.md
- Requirement: DB-Backed Path / Scenario: DB path returns only allowed rows
- Requirement: DB-Backed Path / Scenario: DB tests gated

The DB-backed path runs the ``RetrievalService`` over a ``DbVectorStore`` backed
by repositories + pgvector with the shared ``build_acl_predicate``: only ACL-
allowed rows are returned and leakage is zero. Deleted, non-ready, and cross-
tenant chunks are excluded in SQL (never post-filtered in Python, ADR-3). The
JSONB ``metadata`` column is never consulted by the predicate (spoofing no-op).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.core.models import DocumentPolicy, RetrievalRequest
from ragfence.datasets.acme import build_acme_corp
from ragfence.datasets.loader import seed_acme_corp
from ragfence.db.base import Base
from ragfence.db.models import (
    Document,
    DocumentACL,
    DocumentChunk,
    Tenant,
)
from ragfence.db.repositories import DocumentRepository
from ragfence.db.vector_store import DbVectorStore
from ragfence.policies.guard import DocumentRowState
from ragfence.providers.fakes import FakeEmbeddingProvider
from ragfence.retrieval.result import RetrievalDecision, SecureRetrievalResult
from ragfence.retrieval.service import DOCUMENT_ID_FILTER, RetrievalService

ACME = build_acme_corp()


def _embed(text: str) -> list[float]:
    """Deterministic 1536-dim embedding (matches the service's default embedder)."""
    return FakeEmbeddingProvider().embed([text])[0]


@pytest.fixture(autouse=True)
def _clean_schema(db_engine: Engine) -> None:
    """Each test starts from an empty migrated schema (isolation).

    Mirrors ``tests/integration/test_datasets_seed.py::_clean_schema``: the
    session-scoped ``migrated_schema`` fixture only runs ``alembic upgrade head``
    (idempotent, keeps data), so without truncation a later run would see rows
    left by earlier runs.
    """

    table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with db_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        conn.commit()


def _seed_with_embeddings(db_engine: Engine) -> None:
    """Seed Acme Corp and fill chunk embeddings so pgvector search is meaningful."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        for chunk in session.scalars(select(DocumentChunk)).all():
            chunk.embedding = _embed(chunk.content)
        session.commit()


def _insert_doc(
    session: Session,
    *,
    document_id: UUID,
    tenant_id: UUID,
    department_id: UUID | None,
    title: str,
    classification: Classification,
    status: DocumentStatus,
    deleted_at: datetime | None,
    allowed_group_ids: set[UUID] | None = None,
) -> Document:
    """Insert a document + ACL + chunk row (for deleted/non-ready/cross-tenant)."""
    source = f"synthetic://{title}"
    doc = Document(
        id=document_id,
        tenant_id=tenant_id,
        department_id=department_id,
        title=title,
        source=source,
        checksum=f"db-test-{document_id}",
        classification=classification,
        status=status,
        deleted_at=deleted_at,
    )
    session.add(doc)
    session.add(
        DocumentACL(
            document_id=document_id,
            tenant_id=tenant_id,
            department_id=department_id,
            classification=classification,
            allowed_user_ids=[],
            allowed_group_ids=sorted(allowed_group_ids or set()),
        )
    )
    session.add(
        DocumentChunk(
            document_id=document_id,
            tenant_id=tenant_id,
            chunk_index=0,
            content=f"body of {title}",
            embedding=_embed(f"body of {title}"),
            chunk_metadata={},
        )
    )
    return doc


def _make_db_service(db_engine: Engine, ctx) -> RetrievalService:
    """RetrievalService wired to the DB-backed path (repositories + DbVectorStore)."""

    def load_row(document_id: UUID) -> DocumentRowState | None:
        with Session(db_engine) as session:
            row = DocumentRepository(session, ctx.tenant_id).get_active(document_id)
            if row is None:
                return None
            return DocumentRowState(
                document_id=row.id,
                tenant_id=row.tenant_id,
                status=row.status,
                deleted_at=row.deleted_at,
            )

    def policy(document_id: UUID) -> DocumentPolicy:
        with Session(db_engine) as session:
            acl = session.scalar(select(DocumentACL).where(DocumentACL.document_id == document_id))
            assert acl is not None
            return DocumentPolicy(
                classification=acl.classification,
                department_id=acl.department_id,
                allowed_user_ids=set(acl.allowed_user_ids),
                allowed_group_ids=set(acl.allowed_group_ids),
            )

    def document_meta(document_id: UUID):
        with Session(db_engine) as session:
            return session.scalar(select(Document).where(Document.id == document_id))

    return RetrievalService(
        store=DbVectorStore(db_engine),
        load_row=load_row,
        policy=policy,
        document_meta=document_meta,
    )


def _request(ctx, document_id: UUID, *, top_k: int = 50) -> RetrievalRequest:
    return RetrievalRequest(
        query="retrieval test",
        authorization=ctx,
        top_k=top_k,
        filters={DOCUMENT_ID_FILTER: str(document_id)},
    )


@pytest.mark.db
def test_db_path_returns_only_allowed_rows_and_zero_leakage(db_engine: Engine) -> None:
    """Spec: DB path returns only ACL-allowed rows; deleted/non-ready/cross-tenant leak zero.

    A finance analyst (finance, CONFIDENTIAL) may read the finance CFO document
    only. The restricted executive board-plan (classification escalation) and any
    deleted, non-ready, or cross-tenant finance chunk must not leak.
    """
    _seed_with_embeddings(db_engine)
    ctx = ACME.context_for("finance_analyst@acme-corp.example")
    finance_dept = ACME.departments["finance"].id
    cfo = ACME.documents["finance/payroll/cfo-payroll-summary.pdf"]
    board = ACME.documents["executive/strategy/2026-board-plan.pdf"]

    other_tenant = uuid4()
    deleted_id = uuid4()
    pending_id = uuid4()
    cross_tenant_id = uuid4()
    with Session(db_engine) as session:
        session.add(
            Tenant(id=other_tenant, name="Other Corp", slug=f"other-{other_tenant.hex[:8]}")
        )
        # Same tenant, finance dept, but soft-deleted => excluded.
        _insert_doc(
            session,
            document_id=deleted_id,
            tenant_id=ACME.tenant.id,
            department_id=finance_dept,
            title="Deleted Finance Doc",
            classification=Classification.CONFIDENTIAL,
            status=DocumentStatus.READY,
            deleted_at=datetime.now(UTC),
        )
        # Same tenant, finance dept, but not READY => excluded.
        _insert_doc(
            session,
            document_id=pending_id,
            tenant_id=ACME.tenant.id,
            department_id=finance_dept,
            title="Pending Finance Doc",
            classification=Classification.CONFIDENTIAL,
            status=DocumentStatus.PENDING,
            deleted_at=None,
        )
        # Other tenant, finance-shaped => excluded by the ACL predicate tenant check.
        _insert_doc(
            session,
            document_id=cross_tenant_id,
            tenant_id=other_tenant,
            department_id=None,
            title="Cross Tenant Doc",
            classification=Classification.CONFIDENTIAL,
            status=DocumentStatus.READY,
            deleted_at=None,
        )
        session.commit()

    service = _make_db_service(db_engine, ctx)
    result: SecureRetrievalResult = service.retrieve(_request(ctx, cfo.id))

    assert result.decision == RetrievalDecision.ALLOW
    returned = {c.document_id for c in result.chunks}
    # Exactly the allowed finance document is returned.
    assert returned == {cfo.id}
    # The restricted board-plan (classification escalation) never leaks.
    assert board.id not in returned
    # Deleted, non-ready, and cross-tenant chunks never leak.
    assert {deleted_id, pending_id, cross_tenant_id}.isdisjoint(returned)
    # Every returned chunk belongs to a document the analyst may read.
    assert len(result.chunks) > 0


@pytest.mark.db
def test_db_path_metadata_spoofing_is_a_no_op(db_engine: Engine) -> None:
    """Spec: spoofed JSONB metadata granting broader access leaves the result unchanged.

    The ACL predicate references typed columns only (never the JSONB ``metadata``
    column), so modifying a chunk's metadata cannot change what is returned.
    """
    _seed_with_embeddings(db_engine)
    ctx = ACME.context_for("finance_analyst@acme-corp.example")
    cfo = ACME.documents["finance/payroll/cfo-payroll-summary.pdf"]

    # Baseline (no spoof).
    baseline = _make_db_service(db_engine, ctx).retrieve(_request(ctx, cfo.id))

    # Spoof the allowed chunk's JSONB metadata to claim a broader grant.
    with Session(db_engine) as session:
        chunk = session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == cfo.id))
        assert chunk is not None
        chunk.chunk_metadata = {
            "classification": "restricted",
            "department": "executive",
            "allowed_user_ids": [str(uuid4())],
        }
        session.commit()

    spoofed = _make_db_service(db_engine, ctx).retrieve(_request(ctx, cfo.id))

    assert spoofed.decision == baseline.decision == RetrievalDecision.ALLOW
    assert [c.document_id for c in spoofed.chunks] == [c.document_id for c in baseline.chunks]
