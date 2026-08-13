"""Typed fail-closed identity error tests (PR 1, task 3.1).

Spec reference: openspec/changes/ragfence-auth-context/specs/auth-context/spec.md
- Fail-Closed Typed Errors (R5): unknown identities raise ``IdentityNotFoundError``,
  inactive identities raise ``IdentityInactiveError``, and both are catchable as
  the common ``IdentityError`` base.

The raising paths are covered in their boundary files: unknown-email resolution
in ``test_auth_providers.py`` and provider-failure propagation through the
builder in ``test_auth_builder.py``. This file verifies the error types
themselves: hierarchy, principal-carrying messages, and catchability.
"""

from __future__ import annotations

import pytest

from ragfence.auth.errors import IdentityError, IdentityInactiveError, IdentityNotFoundError

UNKNOWN_EMAIL = "ghost@acme-corp.example"
INACTIVE_EMAIL = "inactive@acme-corp.example"


def test_error_types_subclass_identity_error() -> None:
    assert issubclass(IdentityNotFoundError, IdentityError)
    assert issubclass(IdentityInactiveError, IdentityError)


def test_identity_not_found_error_carries_principal_message() -> None:
    error = IdentityNotFoundError(UNKNOWN_EMAIL)
    assert UNKNOWN_EMAIL in str(error)
    assert isinstance(error, IdentityError)


def test_identity_inactive_error_carries_principal_message() -> None:
    error = IdentityInactiveError(INACTIVE_EMAIL)
    assert INACTIVE_EMAIL in str(error)
    assert isinstance(error, IdentityError)


def test_identity_errors_are_catchable_as_base() -> None:
    with pytest.raises(IdentityError):
        raise IdentityNotFoundError(UNKNOWN_EMAIL)
    with pytest.raises(IdentityError):
        raise IdentityInactiveError(INACTIVE_EMAIL)
