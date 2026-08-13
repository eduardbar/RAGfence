"""In-memory VectorStore test double (design: tests/support/).

Implements the ``VectorStore`` protocol with zero I/O. It holds only
pre-filtered data, so the ``policy_predicate`` argument is accepted for
protocol conformance but never consulted at runtime.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from uuid import UUID

from ragfence.core.models import RetrievedChunk

if TYPE_CHECKING:
    from sqlalchemy.sql import ClauseElement as SQL

    from ragfence.core.protocols import VectorStore


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class InMemoryVectorStore:
    """Zero-I/O VectorStore double ranking stored chunks by cosine similarity."""

    def __init__(self) -> None:
        self._chunks: dict[UUID, tuple[RetrievedChunk, list[float]]] = {}

    def add(self, chunk: RetrievedChunk, embedding: list[float]) -> None:
        self._chunks[chunk.chunk_id] = (chunk, embedding)

    def search(
        self, *, embedding: list[float], policy_predicate: SQL, top_k: int
    ) -> list[RetrievedChunk]:
        ranked = sorted(
            self._chunks.values(),
            key=lambda item: _cosine_similarity(embedding, item[1]),
            reverse=True,
        )
        return [chunk for chunk, _embedding in ranked[:top_k]]


# Static conformance: mypy rejects this assignment if the double diverges from the protocol.
_store: VectorStore = InMemoryVectorStore()
