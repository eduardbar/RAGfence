"""RAGAdapter contract and implementations."""

from .factory import create_adapter
from .generic_http import GenericHTTPAdapter, GenericHTTPConfig, GenericHTTPTransport

__all__ = ["GenericHTTPAdapter", "GenericHTTPConfig", "GenericHTTPTransport", "create_adapter"]
