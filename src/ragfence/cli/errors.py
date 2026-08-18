"""Errors raised by the RAGFence CLI."""


class CliError(RuntimeError):
    """Base class for controlled command failures."""


class RuntimeCommandError(CliError):
    """Raised when a configured command cannot complete."""
