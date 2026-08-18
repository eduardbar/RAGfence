"""Typed construction of configured RAGFence adapters."""

from __future__ import annotations

from ragfence.cli.errors import RuntimeCommandError

from .generic_http import GenericHTTPAdapter, GenericHTTPConfig


def create_adapter(name: str, config: GenericHTTPConfig | None) -> GenericHTTPAdapter:
    """Construct a supported external adapter from its validated config."""
    if name != "generic_http":
        raise RuntimeCommandError(f"unsupported adapter: {name}")
    if config is None:
        raise RuntimeCommandError("missing adapters.generic_http configuration")
    return GenericHTTPAdapter(config)
