"""Typed fail-closed identity errors (auth-context, PR 1, task 1.1).

The builder aborts with a typed exception instead of returning a denied
context: callers map ``IdentityError`` subclasses to a denial before any
retrieval runs (design: Fail-closed exceptions vs denied context).
"""


class IdentityError(Exception):
    """Base class for authorization-context identity failures."""


class IdentityNotFoundError(IdentityError):
    """Raised when the principal resolves to no known identity (fail closed)."""


class IdentityInactiveError(IdentityError):
    """Raised when the resolved identity is inactive (``is_active=false``)."""
