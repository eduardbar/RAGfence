"""Idempotent SQLAlchemy loader for the Acme Corp synthetic dataset (PR 2).

Maps the in-memory :class:`AcmeCorpDataset` onto the ``storage-schema`` rows
(design: loader decision). ``_build_row_plan`` is a pure function — no session,
no I/O — producing FK-ordered row plans that unit tests verify without a
database. ``seed_acme_corp`` persists those rows with get-or-create semantics:
each row is looked up by its natural unique key and skipped when already
present, so re-seeding never duplicates rows, and a single commit keeps the
whole fixture atomic (spec S8, S9).

Enum columns carry the enum MEMBER; the ORM ``values_callable`` (``db.models``)
persists the member's lowercase ``.value`` — the loader never passes raw
strings (design: lowercase enums via ``values_callable``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ragfence.datasets.acme import AcmeCorpDataset, build_acme_corp
from ragfence.datasets.constants import SEED
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

# Placeholder hash for synthetic users: ``users.password_hash`` is NOT NULL with
# no server default. These fixtures never authenticate, so any non-empty marker
# is safe; no login path is ever seeded.
SYNTHETIC_PASSWORD_HASH = "synthetic:no-login"


@dataclass(frozen=True, slots=True)
class RowPlan:
    """One persistable row: entity kind, natural unique key, and column values.

    ``key`` names the get-or-create lookup as ``(column, value)`` pairs matching
    a unique constraint on the target table (e.g. ``tenants.slug``,
    ``users (tenant_id, email)``, ``documents (tenant_id, checksum)``).
    ``values`` holds every column value for the insert; enum columns hold the
    enum member (lowercase persisted via ``values_callable``).
    """

    kind: str
    key: tuple[tuple[str, Any], ...]
    values: dict[str, Any]


def _build_row_plan(ds: AcmeCorpDataset) -> tuple[RowPlan, ...]:
    """Map the dataset onto FK-ordered, natural-keyed row plans (pure, S8).

    Order is dependency-safe — tenant -> departments -> groups -> users ->
    user_groups -> documents -> document_acl -> document_chunks — so inserting
    in plan order never violates a foreign key. Department scope on document
    and ACL rows comes from the ACL (design: single source of truth); the board
    plan has no department on either row (design: board-plan NOT mirrored).
    """

    tenant = ds.tenant
    tenant_plan = RowPlan(
        kind="tenant",
        key=(("slug", tenant.slug),),
        values={"id": tenant.id, "name": tenant.name, "slug": tenant.slug},
    )
    department_plans = [
        RowPlan(
            kind="department",
            key=(("tenant_id", dept.tenant_id), ("slug", dept.slug)),
            values={
                "id": dept.id,
                "tenant_id": dept.tenant_id,
                "name": dept.name,
                "slug": dept.slug,
            },
        )
        for dept in ds.departments.values()
    ]
    group_plans = [
        RowPlan(
            kind="group",
            key=(("tenant_id", group.tenant_id), ("slug", group.slug)),
            values={
                "id": group.id,
                "tenant_id": group.tenant_id,
                "name": group.name,
                "slug": group.slug,
            },
        )
        for group in ds.groups.values()
    ]
    user_plans = [
        RowPlan(
            kind="user",
            key=(("tenant_id", user.tenant_id), ("email", user.email)),
            values={
                "id": user.id,
                "tenant_id": user.tenant_id,
                "department_id": user.department_id,
                "email": user.email,
                "password_hash": SYNTHETIC_PASSWORD_HASH,
                "display_name": user.name,
                "classification": user.classification,
            },
        )
        for user in ds.users.values()
    ]
    user_group_plans = [
        RowPlan(
            kind="user_group",
            key=(("user_id", user_id), ("group_id", group_id)),
            values={"user_id": user_id, "group_id": group_id},
        )
        for user_id, group_id in ds.user_groups
    ]
    document_plans: list[RowPlan] = []
    acl_plans: list[RowPlan] = []
    chunk_plans: list[RowPlan] = []
    for doc in ds.documents.values():
        document_plans.append(
            RowPlan(
                kind="document",
                key=(("tenant_id", doc.tenant_id), ("checksum", doc.checksum)),
                values={
                    "id": doc.id,
                    "tenant_id": doc.tenant_id,
                    "department_id": doc.acl.department_id,
                    "title": doc.title,
                    "source": doc.source,
                    "checksum": doc.checksum,
                    "classification": doc.classification,
                    "status": doc.status,
                },
            )
        )
        acl_plans.append(
            RowPlan(
                kind="document_acl",
                key=(("document_id", doc.id),),
                values={
                    "document_id": doc.id,
                    "tenant_id": doc.tenant_id,
                    "department_id": doc.acl.department_id,
                    "classification": doc.acl.classification,
                    "allowed_user_ids": sorted(doc.acl.allowed_user_ids),
                    "allowed_group_ids": sorted(doc.acl.allowed_group_ids),
                },
            )
        )
        chunk_plans.append(
            RowPlan(
                kind="document_chunk",
                key=(("document_id", doc.id), ("chunk_index", 0)),
                values={
                    "document_id": doc.id,
                    "tenant_id": doc.tenant_id,
                    "chunk_index": 0,
                    "content": doc.body,
                    "embedding": None,
                },
            )
        )
    return (
        tenant_plan,
        *department_plans,
        *group_plans,
        *user_plans,
        *user_group_plans,
        *document_plans,
        *acl_plans,
        *chunk_plans,
    )


_ORM_BY_KIND: dict[str, type[Any]] = {
    "tenant": Tenant,
    "department": Department,
    "group": Group,
    "user": User,
    "user_group": UserGroup,
    "document": Document,
    "document_acl": DocumentACL,
    "document_chunk": DocumentChunk,
}


def _exists(session: Session, plan: RowPlan) -> bool:
    """True when a row with the plan's natural unique key is already present."""
    model = _ORM_BY_KIND[plan.kind]
    stmt = select(model).where(*(getattr(model, column) == value for column, value in plan.key))
    return session.scalar(stmt) is not None


def seed_acme_corp(session: Session) -> None:
    """Idempotently seed the Acme Corp fixture into a migrated schema (S8, S9).

    Every plan row is get-or-created by its natural unique key: existing rows
    are skipped, so re-runs are no-ops and row counts never change. All inserts
    are flushed by the single commit at the end (atomic fixture).
    """
    for plan in _build_row_plan(build_acme_corp(SEED)):
        if _exists(session, plan):
            continue
        session.add(_ORM_BY_KIND[plan.kind](**plan.values))
    session.commit()
