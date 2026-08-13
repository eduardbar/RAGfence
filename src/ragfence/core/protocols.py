"""Pure provider protocols (TRD §3.4, §6-§8).

Protocol definitions only — no I/O, no ORM at runtime. The SQL predicate type
in ``VectorStore`` is referenced under TYPE_CHECKING so ``core`` stays ORM-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ragfence.core.models import LLMResponse, Message, RetrievalRequest, RetrievedChunk

if TYPE_CHECKING:
    from sqlalchemy.sql import ClauseElement as SQL


class RAGAdapter(Protocol):
    """Any RAG system RAGFence can evaluate against (TRD §3.4)."""

    name: str

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]: ...
    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str: ...
    def is_healthy(self) -> bool: ...


class VectorStore(Protocol):
    """Vector search seam; the SQL predicate is built by the storage layer (TRD §6)."""

    def search(
        self, *, embedding: list[float], policy_predicate: SQL, top_k: int
    ) -> list[RetrievedChunk]: ...


class LLMProvider(Protocol):
    """BYOK LLM seam; FakeLLMProvider is the zero-key default (TRD §7)."""

    name: str

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    """BYOK embedding seam (TRD §8)."""

    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...
