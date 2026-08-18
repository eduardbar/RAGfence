"""Release Work Unit 5: disposable PostgreSQL proof, explicitly DB-gated."""

from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.datasets import seed_acme_corp
from ragfence.db.models import Document, Tenant
from tests.integration.conftest import _alembic_config
from tests.integration.test_datasets_seed import EXPECTED_COUNTS, _counts
from tests.integration.test_evaluation_e2e_db import _clean_schema
from tests.integration.test_migrations import _checksum


@pytest.mark.db
def test_release_database_migration_seed_and_traps_are_repeatable(
    postgres_dsn: str, db_engine: Engine
) -> None:
    """Fresh/repeat Alembic plus Acme seed, board-plan trap, and no duplicates."""
    command.upgrade(_alembic_config(postgres_dsn), "head")
    command.upgrade(_alembic_config(postgres_dsn), "head")
    _clean_schema(db_engine)
    with Session(db_engine) as session:
        seed_acme_corp(session)
        first = _counts(session)
        seed_acme_corp(session)
        second = _counts(session)
        board = session.scalar(select(Document).where(Document.title == "2026 Board Plan"))
        assert board is not None and board.department_id is None
    assert first == EXPECTED_COUNTS
    assert second == first


@pytest.mark.db
def test_release_database_tenant_isolation_survives_same_named_documents(db_engine: Engine) -> None:
    """Two tenants may use the same title/checksum without cross-tenant reads."""
    _clean_schema(db_engine)
    with Session(db_engine) as session:
        tenant_a = Tenant(name="Release A", slug="release-a")
        tenant_b = Tenant(name="Release B", slug="release-b")
        session.add_all([tenant_a, tenant_b])
        session.flush()
        session.add_all(
            [
                Document(
                    tenant_id=tenant_a.id,
                    title="same-title",
                    source="release",
                    checksum=_checksum(),
                ),
                Document(
                    tenant_id=tenant_b.id,
                    title="same-title",
                    source="release",
                    checksum=_checksum(),
                ),
            ]
        )
        session.commit()
        assert session.scalar(select(func.count()).select_from(Document)) == 2
        count_a = session.scalar(
            select(func.count()).select_from(Document).where(Document.tenant_id == tenant_a.id)
        )
        count_b = session.scalar(
            select(func.count()).select_from(Document).where(Document.tenant_id == tenant_b.id)
        )
        assert count_a == 1
        assert count_b == 1
