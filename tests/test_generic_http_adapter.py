from __future__ import annotations

from uuid import UUID

import pytest

from ragfence.adapters import GenericHTTPAdapter
from ragfence.adapters.errors import UnsupportedOperationError
from ragfence.adapters.generic_http import GenericHTTPConfig
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, RetrievalRequest, RetrievedChunk


class RecordingTransport:
    def __init__(self, responses: list[object], healthy: bool = True) -> None:
        self.responses = responses
        self.posts: list[tuple[str, object]] = []
        self.healthy = healthy

    def post_json(
        self, path: str, payload: object, *, extra_headers: dict[str, str] | None = None
    ) -> object:
        self.posts.append((path, payload))
        return self.responses.pop(0)

    def health(self) -> bool:
        return self.healthy


REQUEST = RetrievalRequest(
    query="What is the approval policy?",
    top_k=3,
    authorization=AuthorizationContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000010"),
        user_id=UUID("00000000-0000-0000-0000-000000000011"),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    ),
)

CHUNK = RetrievedChunk(
    chunk_id=UUID("00000000-0000-0000-0000-000000000001"),
    document_id=UUID("00000000-0000-0000-0000-000000000002"),
    document_title="Policy",
    chunk_index=2,
    content="Approval is required.",
    score=0.875,
    metadata={"classification": "internal"},
)


def config(**overrides: object) -> GenericHTTPConfig:
    values: dict[str, object] = {
        "base_url": "https://rag.example.test",
        "retrieve_path": "retrieve",
        "answer_path": "answer",
    }
    values.update(overrides)
    return GenericHTTPConfig.model_validate(values)


def test_retrieve_posts_question_and_top_k_and_strictly_maps_response() -> None:
    transport = RecordingTransport(
        [
            {
                "chunks": [
                    {
                        "chunk_id": str(CHUNK.chunk_id),
                        "document_id": str(CHUNK.document_id),
                        "document_title": CHUNK.document_title,
                        "chunk_index": CHUNK.chunk_index,
                        "content": CHUNK.content,
                        "score": CHUNK.score,
                        "metadata": CHUNK.metadata,
                    }
                ]
            }
        ]
    )

    result = GenericHTTPAdapter(config(), transport=transport).retrieve(REQUEST)

    assert transport.posts == [("retrieve", {"question": REQUEST.query, "top_k": REQUEST.top_k})]
    assert result == [CHUNK]


def test_answer_posts_question_and_json_serialized_context_and_maps_answer() -> None:
    transport = RecordingTransport([{"answer": "Approval is required."}])

    result = GenericHTTPAdapter(config(), transport=transport).answer(REQUEST, [CHUNK])

    assert result == "Approval is required."
    assert transport.posts == [
        (
            "answer",
            {
                "question": REQUEST.query,
                "context": [CHUNK.model_dump(mode="json")],
            },
        )
    ]


def test_answer_without_configured_path_is_explicitly_unsupported() -> None:
    adapter = GenericHTTPAdapter(config(answer_path=None), transport=RecordingTransport([]))

    with pytest.raises(UnsupportedOperationError, match="answer"):
        adapter.answer(REQUEST, [CHUNK])


def test_is_healthy_delegates_to_transport() -> None:
    transport = RecordingTransport([], healthy=False)

    assert GenericHTTPAdapter(config(), transport=transport).is_healthy() is False


def test_adapter_exposes_protocol_name() -> None:
    assert GenericHTTPAdapter(config(), transport=RecordingTransport([])).name == "generic_http"
