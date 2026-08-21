"""Repositories: soft-delete and tenant-scoped reads over the ORM models.

``active_filters`` encodes storage rules 1-2 (``deleted_at IS NULL``) and rule 3
(tenant scope) so every read query filters soft-deleted rows and never crosses
tenant boundaries (BACKEND_SCHEMA §8, §17). ``build_acl_predicate`` (BACKEND
SCHEMA §9.1) composes the retrieval access predicate from typed ACL columns only
— the JSONB ``metadata`` column is never consulted.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext
from ragfence.db.models import Document, User, UserGroup


def active_filters(
    model: type[Any],
    *,
    tenant_id: UUID,
    tenant_scoped: bool = True,
) -> list[ColumnElement[bool]]:
    """Row-state WHERE clauses shared by every repository read (rules 1-3).

    Tables without ``deleted_at`` (e.g. ``document_acl``) simply omit the
    soft-delete clause; tables without ``tenant_id`` (``tenants``) omit scope.
    """
    filters: list[ColumnElement[bool]] = []
    deleted_at = getattr(model, "deleted_at", None)
    if deleted_at is not None:
        filters.append(deleted_at.is_(None))
    if tenant_scoped:
        tenant_column = getattr(model, "tenant_id", None)
        if tenant_column is not None:
            filters.append(tenant_column == tenant_id)
    return filters


class BaseRepository[ModelT]:
    """Shared read path: active rows scoped to exactly one tenant."""

    model: type[ModelT]

    def __init__(self, session: Session, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _active_statement(self, *extra: ColumnElement[bool]) -> Select[tuple[ModelT]]:
        """Build a select that always carries the shared row-state filters."""
        return select(self.model).where(
            *active_filters(self.model, tenant_id=self._tenant_id),
            *extra,
        )


class DocumentRepository(BaseRepository[Document]):
    """Document access: active rows for one tenant, never soft-deleted."""

    model = Document

    def list_active(self) -> list[Document]:
        stmt = self._active_statement().order_by(Document.created_at)
        return list(self._session.scalars(stmt))

    def get_active(self, document_id: UUID) -> Document | None:
        stmt = self._active_statement(Document.id == document_id)
        return self._session.scalars(stmt).first()

    def count_active(self) -> int:
        stmt = select(func.count()).where(*active_filters(Document, tenant_id=self._tenant_id))
        return int(self._session.scalar(stmt) or 0)


class UserRepository(BaseRepository[User]):
    """User access: active rows for one tenant, never cross-tenant.

    ``users`` has no ``deleted_at`` (BACKEND_SCHEMA §4), so ``active_filters``
    contributes tenant scope only. ``is_active`` is deliberately NOT filtered
    here — the identity provider inspects it to raise ``IdentityInactiveError``
    (design: fail-closed typed errors), keeping absent and inactive rows
    distinguishable.
    """

    model = User

    def get_active(self, *, user_id: UUID | None = None, email: str | None = None) -> User | None:
        """Return the tenant-scoped user row, or ``None`` when absent.

        Exactly one of ``user_id`` or ``email`` is required; passing both or
        neither is a caller bug and raises ``ValueError``.
        """
        if (user_id is None) == (email is None):
            raise ValueError("get_active requires exactly one of user_id or email")
        if user_id is not None:
            return self._session.scalars(self._active_statement(User.id == user_id)).first()
        return self._session.scalars(self._active_statement(User.email == email)).first()


def group_ids_for_user(session: Session, tenant_id: UUID, user_id: UUID) -> list[UUID]:
    """Group ids for a user from the ``user_groups`` join, tenant-scoped.

    ``user_groups`` has no tenant column, so the scope comes from joining
    through ``users`` (storage rule 3: reads never cross tenant boundaries).
    """
    stmt = (
        select(UserGroup.group_id)
        .join(User, User.id == UserGroup.user_id)
        .where(UserGroup.user_id == user_id, User.tenant_id == tenant_id)
        .order_by(UserGroup.group_id)
    )
    return list(session.scalars(stmt))


def build_acl_predicate(acl: Any, ctx: AuthorizationContext) -> ColumnElement[bool]:
    """Retrieval access predicate from typed ACL columns (BACKEND_SCHEMA §9.1).

    ``acl`` is the ORM ``DocumentACL`` class. The predicate references only
    normalized columns — ``tenant_id``, ``department_id``, ``classification``,
    ``allowed_user_ids``, ``allowed_group_ids`` — and NEVER the JSONB
    ``metadata`` column, keeping the filter surface exact and non-spoofable
    (deny-by-default: no grant and no department match means no access).

    PUBLIC documents are accessible to all tenant users regardless of department.
    """
    classification_rank = case(
        (acl.classification == Classification.PUBLIC, 0),
        (acl.classification == Classification.INTERNAL, 1),
        (acl.classification == Classification.CONFIDENTIAL, 2),
        (acl.classification == Classification.RESTRICTED, 3),
        else_=Classification.RESTRICTED.rank + 1,
    )
    department_match = and_(
        acl.department_id.is_not(None),
        acl.department_id == ctx.department_id,
    )
    public_access = acl.classification == Classification.PUBLIC
    return and_(
        acl.tenant_id == ctx.tenant_id,
        classification_rank <= ctx.classification.rank,
        or_(
            public_access,
            acl.allowed_user_ids.any(ctx.user_id),
            acl.allowed_group_ids.overlap(list(ctx.allowed_group_ids)),
            department_match,
        ),
    )
