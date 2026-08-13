"""Authentication resolution and AuthorizationContext builder (auth-context).

Public API: typed identity errors, the ``AuthenticatedIdentity`` record,
in-memory token registry, identity providers/directory, and the
``build_authorization_context`` orchestrator. The ``AuthorizationContext`` model
contract lives in ``ragfence.core.models`` and is unchanged.
"""

from ragfence.auth.builder import IdentityDirectory, build_authorization_context
from ragfence.auth.errors import IdentityError, IdentityInactiveError, IdentityNotFoundError
from ragfence.auth.identity import AuthenticatedIdentity, IdentityProvider, IdentitySource
from ragfence.auth.providers import (
    AcmeDirectory,
    ApiTokenIdentityProvider,
    SyntheticIdentityProvider,
)
from ragfence.auth.registry import InMemoryTokenRegistry, TokenRegistry

__all__ = [
    "AcmeDirectory",
    "ApiTokenIdentityProvider",
    "AuthenticatedIdentity",
    "IdentityDirectory",
    "IdentityError",
    "IdentityInactiveError",
    "IdentityNotFoundError",
    "IdentityProvider",
    "IdentitySource",
    "InMemoryTokenRegistry",
    "SyntheticIdentityProvider",
    "TokenRegistry",
    "build_authorization_context",
]
