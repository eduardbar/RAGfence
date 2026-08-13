"""DB-gated auth-context integration tests (PR 2, tasks 6.1-6.2).

Skipped with ``PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN`` when no
database is reachable (tests/conftest.py ``postgres_dsn`` probe; the
``migrated_schema``/``db_engine`` fixtures run Alembic to head). Spec reference:
openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- DB-Backed Path / Scenario: Groups derived from user_groups (R4)
- DB-Backed Path / Scenario: DB tests gated (R4)
- Fail-Closed Typed Errors / Scenario: Inactive user (R5)
- Fail-Closed Typed Errors / Scenario: Soft-deleted user denied (R5, defensive)
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.auth.builder import build_authorization_context
from ragfence.auth.db import DbDirectory, DbIdentityProvider
from ragfence.auth.errors import IdentityInactiveError, IdentityNotFoundError
from ragfence.core.enums import Classification
from ragfence.datasets import seed_acme_corp
from ragfence.db.base import Base
from ragfence.db.models import Group, User, UserGroup
from ragfence.db.repositories import active_filters

CFO_EMAIL = "cfo@acme-corp.example"
GHOST_EMAIL = "ghost@acme-corp.example"


@pytest.fixture(autouse=True)
def _clean_schema(db_engine: Engine) -> None:
    """Each DB test starts from an empty schema (isolation).

    The session-scoped ``migrated_schema`` fixture only runs ``alembic upgrade
    head`` (idempotent, keeps data), so without truncation a second run sees
    rows left by earlier runs and seeded lookups would be ambiguous.
    """

    table_names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    with db_engine.connect() as conn:
        conn.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.mark.db
def test_seeded_executives_user_derives_groups_and_lowercase_classification(
    db_engine: Engine,
) -> None:
    """R4: context from a seeded DB user — groups via user_groups, lowercase enum."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        cfo = session.scalar(select(User).where(User.email == CFO_EMAIL))
        assert cfo is not None
        executives = session.scalar(select(Group).where(Group.slug == "executives"))
        assert executives is not None
        ctx = build_authorization_context(
            CFO_EMAIL,
            provider=DbIdentityProvider(session, cfo.tenant_id),
            directory=DbDirectory(session),
        )
    assert ctx.tenant_id == cfo.tenant_id
    assert ctx.user_id == cfo.id
    assert ctx.department_id == cfo.department_id
    assert ctx.classification is Classification.RESTRICTED
    assert ctx.classification.value == "restricted"  # lowercase persisted value
    assert ctx.allowed_user_ids == {cfo.id}
    assert ctx.allowed_group_ids == {executives.id}
    assert ctx.is_authenticated is True
    assert ctx.source == "synthetic"


@pytest.mark.db
def test_inactive_user_fails_closed(db_engine: Engine) -> None:
    """R5: ``is_active=false`` raises ``IdentityInactiveError``, no context."""
    with Session(db_engine) as session:
        seed_acme_corp(session)
        cfo = session.scalar(select(User).where(User.email == CFO_EMAIL))
        assert cfo is not None
        cfo.is_active = False
        session.commit()
        with pytest.raises(IdentityInactiveError):
            build_authorization_context(
                CFO_EMAIL,
                provider=DbIdentityProvider(session, cfo.tenant_id),
                directory=DbDirectory(session),
            )


@pytest.mark.db
def test_soft_deleted_user_denied_without_schema_change(db_engine: Engine) -> None:
    """R5 defensive: a row excluded from the active read fails closed, no schema change.

    ``users`` has no ``deleted_at`` (BACKEND_SCHEMA §4), so the soft-delete
    scenario is satisfied defensively: removing the row from the tenant-scoped
    active read yields ``IdentityNotFoundError``, and ``active_filters`` still
    compiles to tenant scope only (no new column, no migration).
    """
    with Session(db_engine) as session:
        seed_acme_corp(session)
        cfo = session.scalar(select(User).where(User.email == CFO_EMAIL))
        assert cfo is not None
        tenant_id = cfo.tenant_id
        # user_groups.user_id has no ON DELETE CASCADE; clear join rows first.
        session.execute(delete(UserGroup).where(UserGroup.user_id == cfo.id))
        session.delete(cfo)
        session.commit()
        with pytest.raises(IdentityNotFoundError):
            build_authorization_context(
                CFO_EMAIL,
                provider=DbIdentityProvider(session, tenant_id),
                directory=DbDirectory(session),
            )
    # No schema change: the users read filter stays tenant-scoped only.
    filters = active_filters(User, tenant_id=tenant_id)
    assert len(filters) == 1
    sql = str(select(User).where(*filters).compile(dialect=postgresql.dialect()))
    assert "deleted_at" not in sql
