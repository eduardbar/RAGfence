"""DB-gated loader integration tests (PR 2, task 2.4).

Skipped with ``PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN`` when no
database is reachable (tests/conftest.py ``postgres_dsn`` probe; the
``migrated_schema``/``db_engine`` fixtures run Alembic to head). Spec reference:
openspec/changes/ragfence-acme-dataset/specs/synthetic-dataset/spec.md
- DB Loader Path / Scenario: Seeds schema cleanly
- DB Loader Path / Scenario: Idempotent re-seed
- Synthetic Document Corpus: board-plan persists NULL department on both rows
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.datasets import seed_acme_corp, seed_reference_corp
from ragfence.db.base import Base
from ragfence.db.models import (
    Department,
    Document,
    DocumentACL,
    DocumentChunk,
    Group,
    Tenant,
    User,
    UserGroup,
)

SEEDED_TABLES = (
    Tenant,
    Department,
    Group,
    User,
    UserGroup,
    Document,
    DocumentACL,
    DocumentChunk,
)

EXPECTED_COUNTS = {
    "tenants": 1,
    "departments": 5,
    "groups": 2,
    "users": 7,
    "user_groups": 3,
    "documents": 5,
    "document_acl": 5,
    "document_chunks": 5,
}


def _counts(session: Session) -> dict[str, int]:
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model))
        for model in SEEDED_TABLES
    }


@pytest.fixture(autouse=True)
def _clean_schema(db_engine: Engine) -> None:
    """Each seed test starts from an empty schema (isolation).

    The session-scoped ``migrated_schema`` fixture only runs ``alembic upgrade
    head`` (idempotent, keeps data), so without truncation a second run sees
    rows left by earlier runs and the "clean seed" counts fail.
    """

    table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with db_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.mark.db
def test_seed_inserts_all_rows_without_constraint_violations(db_engine: Engine) -> None:
    """S8: clean seed inserts every row; FK/unique/enum constraints hold."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        counts = _counts(session)
    assert counts == EXPECTED_COUNTS


@pytest.mark.db
def test_reseed_leaves_row_counts_unchanged(db_engine: Engine) -> None:
    """S9: a second seed is a no-op — no duplicates, counts unchanged."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        first = _counts(session)
        seed_acme_corp(session)
        second = _counts(session)
    assert first == EXPECTED_COUNTS
    assert second == first


@pytest.mark.db
def test_board_plan_rows_persist_null_department(db_engine: Engine) -> None:
    """Board plan: document AND ACL rows persist NULL department; executives-only."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        board = session.scalar(select(Document).where(Document.title == "2026 Board Plan"))
        assert board is not None
        assert board.department_id is None
        acl = session.scalar(select(DocumentACL).where(DocumentACL.document_id == board.id))
        assert acl is not None
        assert acl.department_id is None
        executives = session.scalar(select(Group).where(Group.slug == "executives"))
        assert executives is not None
        assert acl.allowed_group_ids == [executives.id]
        # Contrast: the four department-scoped documents keep a department on
        # both rows.
        scoped_docs = session.scalars(
            select(Document).where(Document.title != "2026 Board Plan")
        ).all()
        assert len(scoped_docs) == 4
        assert all(doc.department_id is not None for doc in scoped_docs)


@pytest.mark.db
def test_reference_seed_persists_acme_and_globex_identities(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        seed_reference_corp(session)
        tenants = {tenant.slug for tenant in session.scalars(select(Tenant)).all()}
        emails = {user.email for user in session.scalars(select(User)).all()}

    assert tenants == {"acme-corp", "globex-corp"}
    assert "engineering_employee@acme-corp.example" in emails
    assert "engineering_employee@globex-corp.example" in emails


@pytest.mark.db
def test_reference_seed_persists_embeddings_for_every_chunk(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        seed_reference_corp(session)
        chunks = session.scalars(select(DocumentChunk)).all()

    assert chunks
    assert all(chunk.embedding is not None for chunk in chunks)
