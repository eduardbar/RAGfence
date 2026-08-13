"""Authorization context builder (auth-context, PR 1, task 2.2).

``build_authorization_context`` orchestrates the two-layer boundary: the
``IdentityProvider`` resolves the pre-authenticated principal into an
``AuthenticatedIdentity`` (who), then the ``IdentityDirectory`` derives the
``AuthorizationContext`` (what they may see). The principal-only signature makes
client-supplied tenant/department/classification params unreachable (R2).
"""

from __future__ import annotations

from typing import Protocol

from ragfence.auth.identity import AuthenticatedIdentity, IdentityProvider
from ragfence.core.models import AuthorizationContext


class IdentityDirectory(Protocol):
    """Derives a server-side authorization context from an identity record."""

    def lookup(self, identity: AuthenticatedIdentity) -> AuthorizationContext: ...


def build_authorization_context(
    principal: str,
    *,
    provider: IdentityProvider,
    directory: IdentityDirectory,
) -> AuthorizationContext:
    """Resolve the principal (no credential verification) and derive the context."""
    identity = provider.resolve(principal)
    return directory.lookup(identity)
