"""Pure protocol + fake provider tests (task 2.4).

Spec reference: openspec/changes/ragfence-foundation/specs/domain-models/spec.md
- Pure Protocols / Scenario: Protocol conformance
"""

import subprocess
import sys
import uuid
from pathlib import Path
from uuid import UUID

import pytest

from ragfence.core.models import Message, RetrievedChunk
from ragfence.providers.fakes import FakeEmbeddingProvider, FakeLLMProvider
from tests.support.vector_store import InMemoryVectorStore


def _chunk(text: str, document_id: UUID | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        document_title="title",
        chunk_index=0,
        content=text,
        score=0.0,
        metadata={},
    )


def test_fake_llm_echoes_messages_deterministically() -> None:
    provider = FakeLLMProvider()
    assert provider.name == "fake"
    first = provider.complete(messages=[Message(role="user", content="hello")], temperature=0.0)
    second = provider.complete(messages=[Message(role="user", content="hello")], temperature=0.0)
    assert first.content == "hello"
    assert first == second


def test_fake_llm_counts_tokens() -> None:
    provider = FakeLLMProvider()
    response = provider.complete(
        messages=[Message(role="system", content="sys"), Message(role="user", content="usr")],
        temperature=0.5,
    )
    assert response.content == "sys\nusr"
    assert response.prompt_tokens == 6
    assert response.completion_tokens == 7


def test_fake_embedding_dimension_and_determinism() -> None:
    provider = FakeEmbeddingProvider()
    assert provider.name == "fake"
    assert provider.dimension == 1536
    vectors = provider.embed(["hello", "hello", "world"])
    assert len(vectors) == 3
    assert all(len(vector) == 1536 for vector in vectors)
    assert vectors[0] == vectors[1]
    assert vectors[0] != vectors[2]
    assert vectors[0][0] >= 0.0


def test_in_memory_vector_store_ranks_by_similarity() -> None:
    chunk_a = _chunk("alpha")
    chunk_b = _chunk("beta")
    store = InMemoryVectorStore()
    store.add(chunk_a, [1.0, 0.0])
    store.add(chunk_b, [0.0, 1.0])
    top = store.search(embedding=[1.0, 0.0], policy_predicate=None, top_k=1)
    assert [c.chunk_id for c in top] == [chunk_a.chunk_id]
    ranked = store.search(embedding=[1.0, 0.0], policy_predicate=None, top_k=10)
    assert [c.chunk_id for c in ranked] == [chunk_a.chunk_id, chunk_b.chunk_id]


def test_in_memory_vector_store_respects_top_k() -> None:
    store = InMemoryVectorStore()
    chunks = [_chunk(f"c{i}") for i in range(3)]
    for index, chunk in enumerate(chunks):
        store.add(chunk, [float(index), 0.0])
    result = store.search(embedding=[0.0, 1.0], policy_predicate=None, top_k=2)
    assert len(result) == 2


def test_fakes_perform_no_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec: model and protocol definitions must not perform any I/O."""

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("unexpected I/O during pure model use")

    monkeypatch.setattr("builtins.open", _boom)
    monkeypatch.setattr("socket.socket", _boom)
    assert (
        FakeLLMProvider()
        .complete(messages=[Message(role="user", content="x")], temperature=0.0)
        .content
        == "x"
    )
    assert FakeEmbeddingProvider().embed(["x"])[0][0] >= 0.0
    store = InMemoryVectorStore()
    store.add(_chunk("x"), [1.0])
    assert store.search(embedding=[1.0], policy_predicate=None, top_k=1)[0].content == "x"


def test_implementations_conform_to_protocols_under_mypy() -> None:
    """Spec 'Protocol conformance': mypy --strict accepts the implementations."""
    repo_root = Path(__file__).resolve().parents[1]
    targets = [
        "src/ragfence/core/protocols.py",
        "src/ragfence/providers/fakes.py",
        "tests/support/vector_store.py",
    ]
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", *targets],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"mypy --strict rejected implementations:\n{result.stdout}\n{result.stderr}"
    )
