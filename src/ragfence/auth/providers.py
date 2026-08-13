"""Identity providers and the Acme directory (auth-context, PR 1, task 2.1).

- ``SyntheticIdentityProvider``: resolves an Acme email into an identity
  (``source="synthetic"``), pre-checking membership and defensively converting
  ``KeyError`` to ``IdentityNotFoundError`` (design: Synthetic path reuses the
  Acme dataset).
- ``ApiTokenIdentityProvider``: resolves a registered token to its mapped user,
  tagging the identity ``source="api_token"`` (R6).
- ``AcmeDirectory``: the "what may they see" boundary over
  ``AcmeCorpDataset.context_for`` — deterministic and DB-free.
"""

from __future__ import annotations

from dataclasses import replace

from ragfence.auth.errors import IdentityInactiveError, IdentityNotFoundError
from ragfence.auth.identity import AuthenticatedIdentity, IdentityProvider
from ragfence.auth.registry import TokenRegistry
from ragfence.core.models import AuthorizationContext
from ragfence.datasets.acme import AcmeCorpDataset, AcmeUser


class SyntheticIdentityProvider:
    """Resolves an Acme email into an identity without touching a database."""

    def __init__(self, dataset: AcmeCorpDataset) -> None:
        self._dataset = dataset

    def resolve(self, principal: str) -> AuthenticatedIdentity:
        user = self._lookup_user(principal)
        if not user.is_active:
            raise IdentityInactiveError(principal)
        return AuthenticatedIdentity(
            user_id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            source="synthetic",
        )

    def _lookup_user(self, principal: str) -> AcmeUser:
        if principal not in self._dataset.users:
            raise IdentityNotFoundError(principal)
        try:
            return self._dataset.users[principal]
        except KeyError as exc:  # defensive: mapping changed between check and access
            raise IdentityNotFoundError(principal) from exc


class ApiTokenIdentityProvider:
    """Resolves a registered token to its mapped user (``source="api_token"``)."""

    def __init__(self, registry: TokenRegistry, *, user_provider: IdentityProvider) -> None:
        self._registry = registry
        self._user_provider = user_provider

    def resolve(self, principal: str) -> AuthenticatedIdentity:
        email = self._registry.resolve(principal)
        if email is None:
            raise IdentityNotFoundError(principal)
        identity = self._user_provider.resolve(email)
        return replace(identity, source="api_token")


class AcmeDirectory:
    """Directory over the Acme dataset; derives contexts from identity emails.

    ``context_for`` provides the server-shaped ACL values; the context's
    ``source`` reflects how the principal was authenticated (identity source),
    so a token-authenticated principal yields ``source="api_token"`` (R6).
    """

    def __init__(self, dataset: AcmeCorpDataset) -> None:
        self._dataset = dataset

    def lookup(self, identity: AuthenticatedIdentity) -> AuthorizationContext:
        ctx = self._dataset.context_for(identity.email)
        return ctx.model_copy(update={"source": identity.source})
