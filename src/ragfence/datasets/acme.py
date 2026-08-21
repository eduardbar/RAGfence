"""Acme Corp synthetic org model and corpus (PR 1).

Pure, deterministic, I/O-free construction of the Acme Corp fixture:
one tenant, five departments, seven users covering all four classification
tiers, two groups, five documents with ACLs and stable SHA-256 checksums.

Identifiers are ``uuid5`` from the fixed namespace (design: Stable IDs).
Bodies are composed from fixed literal paragraph pools via a seeded
``random.Random`` (design: RNG decision), mirroring the deterministic
``FakeEmbeddingProvider`` pattern so regeneration is byte-identical.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.core.models import AuthorizationContext, DocumentACL, DocumentPolicy
from ragfence.datasets.checksums import canonical_json, sha256_hex
from ragfence.datasets.constants import (
    BODY_PARAGRAPHS,
    DEPARTMENT_NAMES,
    DEPARTMENT_SLUGS,
    GROUP_NAMES,
    GROUP_SLUGS,
    SEED,
    SOURCE,
    TENANT_NAME,
    TENANT_SLUG,
    UUID_NAMESPACE,
)

# (email, display name, department slug, classification tier)
UserSpec = tuple[str, str, str, Classification]
# (path, title, classification, department slug | None, allowed group slugs)
DocumentSpec = tuple[str, str, Classification, str | None, tuple[str, ...]]

USER_SPECS: tuple[UserSpec, ...] = (
    (
        "engineering_employee@acme-corp.example",
        "Alex Rivera",
        "engineering",
        Classification.INTERNAL,
    ),
    ("hr_coordinator@acme-corp.example", "Jamie Chen", "hr", Classification.PUBLIC),
    ("finance_analyst@acme-corp.example", "Priya Sharma", "finance", Classification.CONFIDENTIAL),
    ("legal_counsel@acme-corp.example", "Sam Whitfield", "legal", Classification.RESTRICTED),
    ("ceo@acme-corp.example", "Morgan Ashford", "executive", Classification.RESTRICTED),
    ("cfo@acme-corp.example", "Dana Okoye", "executive", Classification.RESTRICTED),
    ("finance_lead@acme-corp.example", "Toni Blake", "finance", Classification.CONFIDENTIAL),
)

GROUP_MEMBERSHIP: dict[str, tuple[str, ...]] = {
    "executives": ("ceo@acme-corp.example", "cfo@acme-corp.example"),
    "finance-leads": ("finance_lead@acme-corp.example",),
}

DOCUMENT_SPECS: tuple[DocumentSpec, ...] = (
    (
        "engineering/architecture-overview.md",
        "Architecture Overview",
        Classification.INTERNAL,
        "engineering",
        (),
    ),
    ("hr/employee-handbook.md", "Employee Handbook", Classification.PUBLIC, "hr", ()),
    (
        "finance/payroll/cfo-payroll-summary.pdf",
        "CFO Payroll Summary",
        Classification.CONFIDENTIAL,
        "finance",
        (),
    ),
    (
        "legal/vendor-msa.pdf",
        "Vendor Master Services Agreement",
        Classification.CONFIDENTIAL,
        "legal",
        (),
    ),
    (
        "executive/strategy/2026-board-plan.pdf",
        "2026 Board Plan",
        Classification.RESTRICTED,
        None,
        ("executives",),
    ),
)


@dataclass(frozen=True, slots=True)
class AcmeTenant:
    id: UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class AcmeDepartment:
    id: UUID
    tenant_id: UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class AcmeGroup:
    id: UUID
    tenant_id: UUID
    slug: str
    name: str


@dataclass(frozen=True, slots=True)
class AcmeUser:
    id: UUID
    tenant_id: UUID
    department_id: UUID
    email: str
    name: str
    classification: Classification
    # Activation state mirrors ``users.is_active`` (BACKEND_SCHEMA §4); identity
    # resolution must fail closed for deactivated principals.
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class AcmeDocument:
    """A synthetic document with its persisted ACL shape (design: Corpus Shape)."""

    id: UUID
    tenant_id: UUID
    path: str
    title: str
    source: str
    checksum: str
    classification: Classification
    status: DocumentStatus
    body: str
    acl: DocumentACL

    @property
    def policy(self) -> DocumentPolicy:
        """Derived access policy for ``decide()``; the ACL is the single source."""
        return DocumentPolicy(
            classification=self.acl.classification,
            department_id=self.acl.department_id,
            allowed_user_ids=self.acl.allowed_user_ids,
            allowed_group_ids=self.acl.allowed_group_ids,
        )


@dataclass(frozen=True, slots=True)
class AcmeCorpDataset:
    """In-memory Acme Corp fixture; usable with no database (spec: consumption path)."""

    tenant: AcmeTenant
    departments: Mapping[str, AcmeDepartment]
    groups: Mapping[str, AcmeGroup]
    users: Mapping[str, AcmeUser]
    user_groups: tuple[tuple[UUID, UUID], ...]
    documents: Mapping[str, AcmeDocument]

    def context_for(self, email: str) -> AuthorizationContext:
        """Server-shaped synthetic context (``source="synthetic"``) for a user email."""
        user = self.users[email]
        return AuthorizationContext(
            tenant_id=self.tenant.id,
            user_id=user.id,
            department_id=user.department_id,
            classification=user.classification,
            allowed_user_ids={user.id},
            allowed_group_ids={
                group_id for user_id, group_id in self.user_groups if user_id == user.id
            },
            is_authenticated=True,
            source="synthetic",
        )


def _stable_id(kind: str, slug: str) -> UUID:
    """Stable self-describing identifier: uuid5(NS, "acme-corp/{kind}/{slug}")."""
    return uuid5(UUID_NAMESPACE, f"acme-corp/{kind}/{slug}")


def _globex_id(kind: str, slug: str) -> UUID:
    """Stable identifier for the independent Globex fixture tenant."""
    return uuid5(UUID_NAMESPACE, f"globex-corp/{kind}/{slug}")


def _compose_body(seed: int, slug: str, paragraphs: tuple[str, ...]) -> str:
    """Deterministic 1-3 paragraph body from the fixed literal pool.

    Mirrors the FakeEmbeddingProvider determinism pattern: a fresh
    ``random.Random`` seeded from ``sha256(seed, slug)`` makes the selection
    stable, per-document, and independent of construction order.
    """
    rng = random.Random(hashlib.sha256(f"acme-corp:{seed}:{slug}".encode()).digest())
    count = int(rng.random() * min(3, len(paragraphs))) + 1
    return "\n\n".join(paragraphs[:count])


def build_acme_corp(seed: int = SEED) -> AcmeCorpDataset:
    """Build the full deterministic Acme Corp fixture (pure, I/O-free)."""
    tenant = AcmeTenant(
        id=_stable_id("tenant", TENANT_SLUG),
        slug=TENANT_SLUG,
        name=TENANT_NAME,
    )
    departments = {
        slug: AcmeDepartment(
            id=_stable_id("department", slug),
            tenant_id=tenant.id,
            slug=slug,
            name=DEPARTMENT_NAMES[slug],
        )
        for slug in DEPARTMENT_SLUGS
    }
    groups = {
        slug: AcmeGroup(
            id=_stable_id("group", slug),
            tenant_id=tenant.id,
            slug=slug,
            name=GROUP_NAMES[slug],
        )
        for slug in GROUP_SLUGS
    }
    users = {
        email: AcmeUser(
            id=_stable_id("user", email),
            tenant_id=tenant.id,
            department_id=departments[department_slug].id,
            email=email,
            name=name,
            classification=tier,
        )
        for email, name, department_slug, tier in USER_SPECS
    }
    user_groups = tuple(
        (users[email].id, groups[group_slug].id)
        for group_slug, member_emails in GROUP_MEMBERSHIP.items()
        for email in member_emails
    )
    documents: dict[str, AcmeDocument] = {}
    for path, title, classification, department_slug, group_slugs in DOCUMENT_SPECS:
        body = _compose_body(seed, path, BODY_PARAGRAPHS[path])
        document_id = _stable_id("document", path)
        documents[path] = AcmeDocument(
            id=document_id,
            tenant_id=tenant.id,
            path=path,
            title=title,
            source=SOURCE,
            checksum=sha256_hex(canonical_json(body)),
            classification=classification,
            status=DocumentStatus.READY,
            body=body,
            acl=DocumentACL(
                document_id=document_id,
                tenant_id=tenant.id,
                department_id=departments[department_slug].id if department_slug else None,
                classification=classification,
                allowed_user_ids=set(),
                allowed_group_ids={groups[slug].id for slug in group_slugs},
            ),
        )
    return AcmeCorpDataset(
        tenant=tenant,
        departments=departments,
        groups=groups,
        users=users,
        user_groups=user_groups,
        documents=documents,
    )


def build_globex_corp(seed: int = SEED) -> AcmeCorpDataset:
    """Build a deterministic second tenant with real users and documents.

    The schema allows identical corpus content per tenant, but every persisted
    identity, ACL reference, and document identifier is tenant-specific. This
    makes the fixture suitable for exercising the retrieval tenant boundary.
    """
    acme = build_acme_corp(seed)
    tenant = AcmeTenant(
        id=_globex_id("tenant", "globex-corp"), slug="globex-corp", name="Globex Corp"
    )
    departments = {
        slug: AcmeDepartment(
            id=_globex_id("department", slug),
            tenant_id=tenant.id,
            slug=department.slug,
            name=department.name,
        )
        for slug, department in acme.departments.items()
    }
    groups = {
        slug: AcmeGroup(
            id=_globex_id("group", slug),
            tenant_id=tenant.id,
            slug=group.slug,
            name=group.name,
        )
        for slug, group in acme.groups.items()
    }
    user_ids = {
        user.id: _globex_id("user", user.email.split("@", 1)[0]) for user in acme.users.values()
    }
    users = {
        f"{user.email.split('@', 1)[0]}@globex-corp.example": AcmeUser(
            id=user_ids[user.id],
            tenant_id=tenant.id,
            department_id=departments[
                next(
                    slug
                    for slug, department in acme.departments.items()
                    if department.id == user.department_id
                )
            ].id,
            email=f"{user.email.split('@', 1)[0]}@globex-corp.example",
            name=user.name,
            classification=user.classification,
            is_active=user.is_active,
        )
        for user in acme.users.values()
    }
    group_ids = {group.id: groups[slug].id for slug, group in acme.groups.items()}
    user_groups = tuple(
        (user_ids[user_id], group_ids[group_id]) for user_id, group_id in acme.user_groups
    )
    department_ids = {
        department.id: departments[slug].id for slug, department in acme.departments.items()
    }
    documents: dict[str, AcmeDocument] = {}
    for path, document in acme.documents.items():
        document_id = _globex_id("document", path)
        documents[path] = AcmeDocument(
            id=document_id,
            tenant_id=tenant.id,
            path=path,
            title=f"Globex {document.title}",
            source="globex-synthetic",
            checksum=sha256_hex(canonical_json(f"globex-corp:{document.body}")),
            classification=document.classification,
            status=document.status,
            body=document.body,
            acl=DocumentACL(
                document_id=document_id,
                tenant_id=tenant.id,
                department_id=(
                    department_ids[document.acl.department_id]
                    if document.acl.department_id is not None
                    else None
                ),
                classification=document.acl.classification,
                allowed_user_ids={user_ids[user_id] for user_id in document.acl.allowed_user_ids},
                allowed_group_ids={
                    group_ids[group_id] for group_id in document.acl.allowed_group_ids
                },
            ),
        )
    return AcmeCorpDataset(
        tenant=tenant,
        departments=departments,
        groups=groups,
        users=users,
        user_groups=user_groups,
        documents=documents,
    )
