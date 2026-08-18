"""Typed errors for the generic HTTP adapter boundary."""

from __future__ import annotations


class GenericHTTPError(RuntimeError):
    """Base class for safe, operation-scoped generic HTTP failures."""

    def __init__(self, operation: str, message: str) -> None:
        self.operation = operation
        super().__init__(f"{operation}: {message}")


class GenericHTTPParseError(GenericHTTPError):
    """Raised when a target response cannot be mapped to a wire contract."""


class AdapterError(GenericHTTPError):
    """Compatibility name for adapter-level failures."""


class AdapterParseError(GenericHTTPParseError, AdapterError):
    """The target response was not valid for the operation contract."""


class AdapterTransportError(AdapterError):
    """The target returned an unsuccessful HTTP status."""

    def __init__(self, operation: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(operation, f"target returned HTTP {status_code}")


class UnsupportedOperationError(AdapterError):
    """The configured target does not support an optional operation."""

    def __init__(self, operation: str) -> None:
        super().__init__(operation, "operation is not configured")
