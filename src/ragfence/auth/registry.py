"""API-token registry (auth-context, PR 1, task 1.3).

In-memory server-side registry mapping token to user key (email). The
``TokenRegistry`` protocol keeps the provider decoupled from the storage
backend: a DB-backed token store can replace ``InMemoryTokenRegistry`` without
touching ``ApiTokenIdentityProvider`` (design: In-memory token registry MVP).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class TokenRegistry(Protocol):
    """Resolves a token to its mapped user key (email), or ``None`` when unknown."""

    def resolve(self, token: str) -> str | None: ...


class InMemoryTokenRegistry:
    """MVP token -> user key mapping; swappable for a DB-backed store later."""

    def __init__(self, tokens: Mapping[str, str]) -> None:
        self._tokens = dict(tokens)

    def resolve(self, token: str) -> str | None:
        return self._tokens.get(token)
