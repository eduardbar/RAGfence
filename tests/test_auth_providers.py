"""Synthetic identity provider tests (PR 1, task 3.2).

Spec reference: openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- Server-Side Context Derivation / Scenario: Engineering user from Acme (R2)
- Synthetic Path / Scenario: Deterministic and DB-free (R3)
- Synthetic Path / Scenario: Unknown email fails closed (R3)

The synthetic path is pure: it maps the in-memory Acme dataset, so these tests
run with no database, no DSN, and no fixtures. Determinism is proven by
rebuilding the context twice and asserting byte-for-byte equality.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ragfence.auth.builder import build_authorization_context
from ragfence.auth.errors import IdentityInactiveError, IdentityNotFoundError
from ragfence.auth.providers import (
    AcmeDirectory,
    ApiTokenIdentityProvider,
    SyntheticIdentityProvider,
)
from ragfence.auth.registry import InMemoryTokenRegistry
from ragfence.core.enums import Classification
from ragfence.datasets import SEED, build_acme_corp

ENGINEERING_EMAIL = "engineering_employee@acme-corp.example"
CFO_EMAIL = "cfo@acme-corp.example"
UNKNOWN_EMAIL = "ghost@acme-corp.example"


def _inactive_dataset(email: str = ENGINEERING_EMAIL):
    ds = build_acme_corp(SEED)
    users = dict(ds.users)
    users[email] = replace(users[email], is_active=False)
    return replace(ds, users=users)


def test_engineering_user_derives_server_side_context() -> None:
    ds = build_acme_corp(SEED)
    ctx = build_authorization_context(
        ENGINEERING_EMAIL,
        provider=SyntheticIdentityProvider(ds),
        directory=AcmeDirectory(ds),
    )
    assert ctx.tenant_id == ds.tenant.id
    assert ctx.department_id == ds.departments["engineering"].id
    assert ctx.classification is Classification.INTERNAL
    assert ctx.source == "synthetic"
    assert ctx.is_authenticated is True
    assert ctx.allowed_user_ids == {ds.users[ENGINEERING_EMAIL].id}
    # Engineering employee is in no group per GROUP_MEMBERSHIP; the CFO test
    # below proves non-empty group derivation through the same code path.
    assert ctx.allowed_group_ids == set()


def test_group_member_derives_user_groups_membership() -> None:
    ds = build_acme_corp(SEED)
    ctx = build_authorization_context(
        CFO_EMAIL,
        provider=SyntheticIdentityProvider(ds),
        directory=AcmeDirectory(ds),
    )
    assert ctx.department_id == ds.departments["executive"].id
    assert ctx.classification is Classification.RESTRICTED
    assert ctx.allowed_group_ids == {ds.groups["executives"].id}
    assert ctx.source == "synthetic"


def test_provider_resolves_identity_with_synthetic_source() -> None:
    ds = build_acme_corp(SEED)
    identity = SyntheticIdentityProvider(ds).resolve(ENGINEERING_EMAIL)
    assert identity.user_id == ds.users[ENGINEERING_EMAIL].id
    assert identity.tenant_id == ds.tenant.id
    assert identity.email == ENGINEERING_EMAIL
    assert identity.source == "synthetic"


def test_context_is_deterministic_across_calls() -> None:
    ds = build_acme_corp(SEED)
    provider = SyntheticIdentityProvider(ds)
    directory = AcmeDirectory(ds)
    first = build_authorization_context(CFO_EMAIL, provider=provider, directory=directory)
    second = build_authorization_context(CFO_EMAIL, provider=provider, directory=directory)
    assert first == second
    assert first.allowed_group_ids == {ds.groups["executives"].id}


def test_unknown_email_fails_closed() -> None:
    ds = build_acme_corp(SEED)
    with pytest.raises(IdentityNotFoundError):
        build_authorization_context(
            UNKNOWN_EMAIL,
            provider=SyntheticIdentityProvider(ds),
            directory=AcmeDirectory(ds),
        )


def test_inactive_user_fails_closed_via_synthetic_provider() -> None:
    """R5: deactivated principals must NOT resolve to an authenticated context."""
    ds = _inactive_dataset()
    with pytest.raises(IdentityInactiveError):
        SyntheticIdentityProvider(ds).resolve(ENGINEERING_EMAIL)


def test_inactive_user_fails_closed_through_builder() -> None:
    ds = _inactive_dataset()
    with pytest.raises(IdentityInactiveError):
        build_authorization_context(
            ENGINEERING_EMAIL,
            provider=SyntheticIdentityProvider(ds),
            directory=AcmeDirectory(ds),
        )


def test_inactive_user_fails_closed_via_api_token_path() -> None:
    ds = _inactive_dataset(CFO_EMAIL)
    registry = InMemoryTokenRegistry({"tok-123": CFO_EMAIL})
    provider = ApiTokenIdentityProvider(registry, user_provider=SyntheticIdentityProvider(ds))
    with pytest.raises(IdentityInactiveError):
        provider.resolve("tok-123")
