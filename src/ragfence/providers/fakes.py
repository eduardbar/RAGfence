"""Deterministic, zero-I/O provider implementations (TRD §7, §8).

Used in tests and whenever no API key is present; pure and repeatable.
"""

from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

from ragfence.core.models import LLMResponse, Message

if TYPE_CHECKING:
    from ragfence.core.protocols import EmbeddingProvider, LLMProvider


class FakeLLMProvider:
    """Echoes the joined message content verbatim."""

    name = "fake"

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse:
        content = "\n".join(message.content for message in messages)
        return LLMResponse(
            content=content,
            prompt_tokens=sum(len(message.content) for message in messages),
            completion_tokens=len(content),
        )


class FakeEmbeddingProvider:
    """Stable per-text pseudo-random vectors in [0, 1) of fixed dimension."""

    name = "fake"
    dimension = 1536

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    @staticmethod
    def _embed_text(text: str) -> list[float]:
        rng = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
        return [rng.random() for _ in range(FakeEmbeddingProvider.dimension)]


# Static conformance: mypy rejects these if the fakes diverge from the protocols.
_llm_provider: LLMProvider = FakeLLMProvider()
_embedding_provider: EmbeddingProvider = FakeEmbeddingProvider()
