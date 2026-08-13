"""DB-backed identity provider and directory (auth-context, PR 2, task 5.2).

- ``DbIdentityProvider``: resolves an email against the tenant-scoped ``users``
  table via ``UserRepository``, failing closed with ``IdentityNotFoundError``
  (absent row) or ``IdentityInactiveError`` (``is_active=false``) (R4/R5).
- ``DbDirectory``: derives the ``AuthorizationContext`` from the user row and
  ``user_groups`` membership via repositories — the same seam pattern as
  ``AcmeDirectory``, with lowercase enum values persisted by ``values_callable``
  (design: DB path group derivation via ``user_groups`` join).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from ragfence.auth.errors import IdentityInactiveError, IdentityNotFoundError
from ragfence.auth.identity import AuthenticatedIdentity
from ragfence.core.models import AuthorizationContext
from ragfence.db.repositories import UserRepository, group_ids_for_user


class DbIdentityProvider:
    """Resolves an email into an identity from the ``users`` table (tenant-scoped).

    The tenant is fixed at construction (single-tenant MVP: server-side Acme
    constant); ``is_active`` is inspected so deactivated principals fail closed
    with ``IdentityInactiveError`` before any directory lookup (R5).
    """

    def __init__(self, session: Session, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def resolve(self, principal: str) -> AuthenticatedIdentity:
        user = UserRepository(self._session, self._tenant_id).get_active(email=principal)
        if user is None:
            raise IdentityNotFoundError(principal)
        if not user.is_active:
            raise IdentityInactiveError(principal)
        return AuthenticatedIdentity(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            source="synthetic",
        )


class DbDirectory:
    """Directory over the DB repositories; derives contexts from user rows.

    ``source`` carries over from the identity (mirrors ``AcmeDirectory``), so a
    token-authenticated principal keeps ``source="api_token"`` (R6).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(self, identity: AuthenticatedIdentity) -> AuthorizationContext:
        user = UserRepository(self._session, identity.tenant_id).get_active(
            user_id=identity.user_id
        )
        if user is None:
            raise IdentityNotFoundError(identity.email)
        group_ids = group_ids_for_user(self._session, identity.tenant_id, identity.user_id)
        return AuthorizationContext(
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            department_id=user.department_id,
            classification=user.classification,
            allowed_user_ids={identity.user_id},
            allowed_group_ids=set(group_ids),
            is_authenticated=True,
            source=identity.source,
        )
