"""Authorization context builder tests (PR 1, task 3.4).

Spec reference: openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- Pre-Authenticated Principal Only / Scenario: Builder never authenticates (R1)
- Server-Side Context Derivation / Scenario: Client params ignored (R2)

Recording doubles prove the builder's only interactions are ``provider.resolve``
followed by ``directory.lookup`` — no credential verification, no client-side
derivation. The principal-only signature makes client tenant/classification
params unreachable: passing them raises ``TypeError``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from ragfence.auth.builder import build_authorization_context
from ragfence.auth.errors import IdentityError, IdentityInactiveError
from ragfence.auth.identity import AuthenticatedIdentity
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext

PRINCIPAL = "engineering_employee@acme-corp.example"
INACTIVE_EMAIL = "inactive@acme-corp.example"


class RecordingIdentityProvider:
    """Records every principal handed to ``resolve`` (proves verbatim pass-through)."""

    def __init__(self, identity: AuthenticatedIdentity) -> None:
        self._identity = identity
        self.resolved: list[str] = []

    def resolve(self, principal: str) -> AuthenticatedIdentity:
        self.resolved.append(principal)
        return self._identity


class RecordingIdentityDirectory:
    """Fake ``IdentityDirectory``: records the identity and returns a fixed context."""

    def __init__(self, ctx: AuthorizationContext) -> None:
        self._ctx = ctx
        self.looked_up: list[AuthenticatedIdentity] = []

    def lookup(self, identity: AuthenticatedIdentity) -> AuthorizationContext:
        self.looked_up.append(identity)
        return self._ctx


class _InactiveIdentityProvider:
    """Fails one principal with ``IdentityInactiveError`` (R5 propagation seam)."""

    def __init__(self, identity: AuthenticatedIdentity) -> None:
        self._identity = identity

    def resolve(self, principal: str) -> AuthenticatedIdentity:
        if principal == INACTIVE_EMAIL:
            raise IdentityInactiveError(principal)
        return self._identity


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email=PRINCIPAL,
        source="synthetic",
    )


def _server_context() -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )


def test_builder_resolves_then_looks_up_and_returns_directory_context() -> None:
    identity = _identity()
    ctx = _server_context()
    provider = RecordingIdentityProvider(identity)
    directory = RecordingIdentityDirectory(ctx)
    result = build_authorization_context(PRINCIPAL, provider=provider, directory=directory)
    assert provider.resolved == [PRINCIPAL]  # principal forwarded untouched
    assert directory.looked_up == [identity]  # exact resolved identity handed over
    assert result is ctx  # builder adds nothing; context is server-derived


def test_builder_never_authenticates() -> None:
    """R1: no credential verification — resolve/lookup is the whole pipeline."""
    identity = _identity()
    provider = RecordingIdentityProvider(identity)
    ctx = _server_context()
    directory = RecordingIdentityDirectory(ctx)
    result = build_authorization_context(PRINCIPAL, provider=provider, directory=directory)
    assert result == ctx
    assert provider.resolved == [PRINCIPAL]


def test_client_tenant_param_is_unreachable() -> None:
    with pytest.raises(TypeError):
        build_authorization_context(
            PRINCIPAL,
            provider=RecordingIdentityProvider(_identity()),
            directory=RecordingIdentityDirectory(_server_context()),
            tenant_id=uuid4(),
        )


def test_client_classification_param_is_unreachable() -> None:
    with pytest.raises(TypeError):
        build_authorization_context(
            PRINCIPAL,
            provider=RecordingIdentityProvider(_identity()),
            directory=RecordingIdentityDirectory(_server_context()),
            classification=Classification.CONFIDENTIAL,
        )


def test_builder_propagates_typed_provider_failures() -> None:
    """R5: inactive-identity failures pass through the builder, catchable as base."""
    with pytest.raises(IdentityError) as exc_info:
        build_authorization_context(
            INACTIVE_EMAIL,
            provider=_InactiveIdentityProvider(_identity()),
            directory=RecordingIdentityDirectory(_server_context()),
        )
    assert isinstance(exc_info.value, IdentityInactiveError)
