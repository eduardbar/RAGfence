"""API-token registry tests (PR 1, task 3.3).

Spec reference: openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- API-Token Registry (In-Memory) / Scenario: Registered token resolves (R6)
- API-Token Registry (In-Memory) / Scenario: Unknown token fails closed (R6)

``FakeTokenRegistry`` implements only ``TokenRegistry.resolve`` and is accepted by
``ApiTokenIdentityProvider`` — proving the provider depends on the protocol, not
the concrete in-memory class.
"""

from __future__ import annotations

import pytest

from ragfence.auth.builder import build_authorization_context
from ragfence.auth.errors import IdentityNotFoundError
from ragfence.auth.providers import (
    AcmeDirectory,
    ApiTokenIdentityProvider,
    SyntheticIdentityProvider,
)
from ragfence.auth.registry import InMemoryTokenRegistry
from ragfence.datasets import SEED, build_acme_corp

ENGINEERING_EMAIL = "engineering_employee@acme-corp.example"
REGISTERED_TOKEN = "tok-7f3a9c21"
UNKNOWN_TOKEN = "tok-deadbeef"


class FakeTokenRegistry:
    """Protocol stub: structurally satisfies ``TokenRegistry``."""

    def __init__(self, token: str, email: str) -> None:
        self._token = token
        self._email = email

    def resolve(self, token: str) -> str | None:
        if token == self._token:
            return self._email
        return None


def _provider(ds, registry) -> ApiTokenIdentityProvider:
    return ApiTokenIdentityProvider(registry, user_provider=SyntheticIdentityProvider(ds))


def test_registered_token_resolves_api_token_identity() -> None:
    ds = build_acme_corp(SEED)
    registry = InMemoryTokenRegistry({REGISTERED_TOKEN: ENGINEERING_EMAIL})
    identity = _provider(ds, registry).resolve(REGISTERED_TOKEN)
    assert identity.email == ENGINEERING_EMAIL
    assert identity.source == "api_token"
    assert identity.user_id == ds.users[ENGINEERING_EMAIL].id
    assert identity.tenant_id == ds.tenant.id


def test_registered_token_builds_api_token_context() -> None:
    ds = build_acme_corp(SEED)
    registry = InMemoryTokenRegistry({REGISTERED_TOKEN: ENGINEERING_EMAIL})
    ctx = build_authorization_context(
        REGISTERED_TOKEN,
        provider=_provider(ds, registry),
        directory=AcmeDirectory(ds),
    )
    assert ctx.source == "api_token"
    assert ctx.tenant_id == ds.tenant.id
    assert ctx.user_id == ds.users[ENGINEERING_EMAIL].id
    assert ctx.department_id == ds.departments["engineering"].id


def test_unknown_token_fails_closed() -> None:
    ds = build_acme_corp(SEED)
    registry = InMemoryTokenRegistry({REGISTERED_TOKEN: ENGINEERING_EMAIL})
    with pytest.raises(IdentityNotFoundError):
        _provider(ds, registry).resolve(UNKNOWN_TOKEN)


def test_provider_accepts_any_token_registry_protocol() -> None:
    ds = build_acme_corp(SEED)
    registry = FakeTokenRegistry(REGISTERED_TOKEN, ENGINEERING_EMAIL)
    identity = _provider(ds, registry).resolve(REGISTERED_TOKEN)
    assert identity.source == "api_token"
    assert identity.email == ENGINEERING_EMAIL
