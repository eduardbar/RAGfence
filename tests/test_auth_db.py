"""DB-backed identity provider/directory tests (PR 2, task 5.1) — fake session, no DB.

Spec reference: openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- DB-Backed Path / Scenario: Groups derived from user_groups (R4)
- Fail-Closed Typed Errors / Scenario: Inactive user (R5)
- Fail-Closed Typed Errors / Scenario: Soft-deleted user denied (R5, defensive)

The session is a recording double that serves one user row, then group ids —
the same read surface ``UserRepository`` and ``group_ids_for_user`` exercise —
so the provider/directory logic is verified without a database.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest

from ragfence.auth.db import DbDirectory, DbIdentityProvider
from ragfence.auth.errors import IdentityInactiveError, IdentityNotFoundError
from ragfence.auth.identity import AuthenticatedIdentity
from ragfence.core.enums import Classification

EMAIL = "cfo@acme-corp.example"
UNKNOWN_EMAIL = "ghost@acme-corp.example"


class _UserStub:
    """Minimal user-shaped row double (mirrors the ORM ``User`` surface)."""

    def __init__(
        self,
        *,
        user_id: UUID,
        tenant_id: UUID,
        email: str,
        is_active: bool = True,
        department_id: UUID | None = None,
        classification: Classification = Classification.INTERNAL,
    ) -> None:
        self.id = user_id
        self.tenant_id = tenant_id
        self.email = email
        self.is_active = is_active
        self.department_id = department_id
        self.classification = classification


class _FakeScalars:
    """Iterable/first()-able result double (mirrors tests/test_repositories.py)."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def __iter__(self) -> Iterator[Any]:
        return iter(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Session double serving one user row, then group ids, per statement."""

    def __init__(self, *, user: _UserStub | None = None, group_ids: Sequence[UUID] = ()) -> None:
        self._user = user
        self._group_ids = list(group_ids)
        self.statements: list[Any] = []

    def scalars(self, stmt: Any) -> _FakeScalars:
        self.statements.append(stmt)
        if self._user is not None:
            user, self._user = self._user, None
            return _FakeScalars([user])
        return _FakeScalars(self._group_ids)


def test_db_provider_resolves_active_user_identity() -> None:
    tenant_id, user_id = uuid4(), uuid4()
    session = _FakeSession(user=_UserStub(user_id=user_id, tenant_id=tenant_id, email=EMAIL))
    identity = DbIdentityProvider(session, tenant_id=tenant_id).resolve(EMAIL)
    assert identity.user_id == user_id
    assert identity.tenant_id == tenant_id
    assert identity.email == EMAIL
    assert identity.source == "synthetic"


def test_db_provider_inactive_user_fails_closed() -> None:
    tenant_id, user_id = uuid4(), uuid4()
    session = _FakeSession(
        user=_UserStub(user_id=user_id, tenant_id=tenant_id, email=EMAIL, is_active=False)
    )
    with pytest.raises(IdentityInactiveError):
        DbIdentityProvider(session, tenant_id=tenant_id).resolve(EMAIL)


def test_db_provider_unknown_email_fails_closed() -> None:
    session = _FakeSession(user=None)
    with pytest.raises(IdentityNotFoundError):
        DbIdentityProvider(session, tenant_id=uuid4()).resolve(UNKNOWN_EMAIL)


def test_db_directory_derives_context_from_user_and_groups() -> None:
    tenant_id, user_id, department_id = uuid4(), uuid4(), uuid4()
    group_ids = [uuid4(), uuid4()]
    user = _UserStub(
        user_id=user_id,
        tenant_id=tenant_id,
        email=EMAIL,
        department_id=department_id,
        classification=Classification.RESTRICTED,
    )
    directory = DbDirectory(_FakeSession(user=user, group_ids=group_ids))
    identity = AuthenticatedIdentity(
        user_id=user_id, tenant_id=tenant_id, email=EMAIL, source="synthetic"
    )
    ctx = directory.lookup(identity)
    assert ctx.tenant_id == tenant_id
    assert ctx.user_id == user_id
    assert ctx.department_id == department_id
    assert ctx.classification is Classification.RESTRICTED
    assert ctx.allowed_user_ids == {user_id}
    assert ctx.allowed_group_ids == set(group_ids)
    assert ctx.is_authenticated is True
    assert ctx.source == "synthetic"


def test_db_directory_fails_closed_when_user_row_missing() -> None:
    """R5 defensive: a row absent from the active read fails closed as not-found."""
    tenant_id, user_id = uuid4(), uuid4()
    directory = DbDirectory(_FakeSession(user=None))
    identity = AuthenticatedIdentity(
        user_id=user_id, tenant_id=tenant_id, email=EMAIL, source="synthetic"
    )
    with pytest.raises(IdentityNotFoundError):
        directory.lookup(identity)
