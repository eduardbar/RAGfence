"""Repository filter tests (task 4.4, no DB).

Spec reference: openspec/changes/ragfence-foundation/specs/storage-schema/spec.md
- Soft Delete Semantics / Scenario: Deleted rows excluded (filter builder side)
- Repositories / Scenario: Tenant isolation (filter builder side)

The WHERE-clause builder is exercised against the ORM metadata and compiled to
PostgreSQL SQL without a database; a session double proves the repository passes
those filters into every read statement.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext
from ragfence.db.models import (
    Document,
    Tenant,
)
from ragfence.db.models import (
    DocumentACL as DocumentACLModel,
)
from ragfence.db.repositories import (
    BaseRepository,
    DocumentRepository,
    UserRepository,
    active_filters,
    build_acl_predicate,
    group_ids_for_user,
)

TENANT_A = "0c9f9f62-7a7d-4a8b-9f2e-6c1b3a0d2f01"
TENANT_B = "5d3e4a21-8b2c-4f6d-9e1a-2c4b6d8e0f12"


def _sql(stmt: Any) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_active_filters_apply_soft_delete_and_tenant_scope() -> None:
    filters = active_filters(Document, tenant_id=TENANT_A)
    assert len(filters) == 2
    stmt = select(Document).where(*filters)
    sql = _sql(stmt)
    assert "documents.deleted_at IS NULL" in sql
    assert "documents.tenant_id =" in sql
    params = stmt.compile(dialect=postgresql.dialect()).params
    assert TENANT_A in params.values()


def test_active_filters_omit_deleted_at_when_table_has_none() -> None:
    # document_acl has no deleted_at column: only the tenant scope remains.
    filters = active_filters(DocumentACLModel, tenant_id=TENANT_A)
    assert len(filters) == 1
    sql = _sql(select(DocumentACLModel).where(*filters))
    assert "document_acl.tenant_id =" in sql
    assert "deleted_at" not in sql


def test_active_filters_are_empty_for_tenants_table() -> None:
    # tenants has neither deleted_at nor tenant_id: no spurious filters.
    filters = active_filters(Tenant, tenant_id=TENANT_A)
    assert len(filters) == 0
    sql = _sql(select(Tenant).where(*filters))
    assert "where" not in sql.lower()


class _FakeScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def __iter__(self) -> Any:
        return iter(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Minimal session double that records every statement it receives."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.statements: list[Any] = []

    def scalars(self, stmt: Any) -> _FakeScalars:
        self.statements.append(stmt)
        return _FakeScalars(self._rows)

    def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return len(self._rows)


def test_document_repository_list_active_scopes_and_filters() -> None:
    session = _FakeSession([object(), object()])
    repo = DocumentRepository(session, tenant_id=TENANT_B)
    rows = repo.list_active()
    assert list(rows) == session._rows  # the double returns the rows it was given
    sql = _sql(session.statements[-1])
    assert "documents.deleted_at IS NULL" in sql
    assert "documents.tenant_id =" in sql


def test_document_repository_get_active_adds_id_and_active_filters() -> None:
    session = _FakeSession([object()])
    repo = DocumentRepository(session, tenant_id=TENANT_A)
    target = "11111111-2222-4333-8444-555555555555"
    row = repo.get_active(target)
    assert row is session._rows[0]
    sql = _sql(session.statements[-1])
    assert "documents.id =" in sql
    assert "documents.deleted_at IS NULL" in sql
    assert "documents.tenant_id =" in sql


def test_document_repository_count_active_applies_filters() -> None:
    session = _FakeSession([1])
    repo = DocumentRepository(session, tenant_id=TENANT_B)
    assert repo.count_active() == 1
    sql = _sql(session.statements[-1])
    assert "count(" in sql
    assert "deleted_at IS NULL" in sql
    assert "tenant_id =" in sql


def test_base_repository_exposes_shared_read_path() -> None:
    class _TenantScopedRepo(BaseRepository[Document]):
        model = Document

    session = _FakeSession([])
    repo = _TenantScopedRepo(session, tenant_id=TENANT_A)
    stmt = repo._active_statement()  # noqa: SLF001  (test seam: shared filter path)
    sql = _sql(stmt)
    assert "deleted_at IS NULL" in sql
    assert "tenant_id =" in sql


def test_user_repository_get_active_by_email_scopes_to_tenant() -> None:
    session = _FakeSession([object()])
    repo = UserRepository(session, tenant_id=TENANT_A)
    row = repo.get_active(email="ceo@acme-corp.example")
    assert row is session._rows[0]
    sql = _sql(session.statements[-1])
    assert "users.email =" in sql
    assert "users.tenant_id =" in sql


def test_user_repository_get_active_by_id_scopes_to_tenant() -> None:
    session = _FakeSession([object()])
    repo = UserRepository(session, tenant_id=TENANT_A)
    target = "11111111-2222-4333-8444-555555555555"
    row = repo.get_active(user_id=target)
    assert row is session._rows[0]
    sql = _sql(session.statements[-1])
    assert "users.id =" in sql
    assert "users.tenant_id =" in sql


def test_user_repository_get_active_unknown_email_returns_none() -> None:
    session = _FakeSession([])
    repo = UserRepository(session, tenant_id=TENANT_A)
    assert repo.get_active(email="ghost@acme-corp.example") is None


def test_user_repository_get_active_requires_exactly_one_lookup_key() -> None:
    session = _FakeSession([])
    repo = UserRepository(session, tenant_id=TENANT_A)
    with pytest.raises(ValueError):
        repo.get_active()
    with pytest.raises(ValueError):
        repo.get_active(user_id=TENANT_B, email="ghost@acme-corp.example")


def test_group_ids_for_user_joins_user_groups_with_tenant_scope() -> None:
    session = _FakeSession(
        [
            UUID("11111111-2222-4333-8444-555555555555"),
            UUID("22222222-3333-4444-8555-666666666666"),
        ]
    )
    target = "33333333-4444-4555-8666-777777777777"
    group_ids = group_ids_for_user(session, tenant_id=TENANT_A, user_id=target)
    assert group_ids == session._rows
    sql = _sql(session.statements[-1])
    assert "user_groups" in sql
    assert "users" in sql  # tenant scope joins through the users table
    assert "users.tenant_id =" in sql
    assert "user_groups.user_id =" in sql


def test_acl_predicate_treats_unknown_classifications_as_most_restrictive() -> None:
    ctx = AuthorizationContext(
        tenant_id=UUID(TENANT_A),
        user_id=UUID("33333333-4444-4555-8666-777777777777"),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )

    statement = select(DocumentACLModel).where(build_acl_predicate(DocumentACLModel, ctx))
    params = statement.compile(dialect=postgresql.dialect()).params

    assert 4 in params.values()
