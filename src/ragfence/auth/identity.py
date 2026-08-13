"""Authentication boundary types (auth-context, PR 1, task 1.2).

``AuthenticatedIdentity`` is the "who" record produced by the authentication
boundary; ``IdentityProvider`` resolves a pre-authenticated principal (email or
token) into it. Providers NEVER verify credentials — they map a principal to a
server-side identity record (design: Authentication/authorization separation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

IdentitySource = Literal["synthetic", "oidc", "api_token"]


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    """A resolved, pre-authenticated principal (who)."""

    user_id: UUID
    tenant_id: UUID
    email: str
    source: IdentitySource


class IdentityProvider(Protocol):
    """Resolves a principal string into a server-side identity record."""

    def resolve(self, principal: str) -> AuthenticatedIdentity: ...
