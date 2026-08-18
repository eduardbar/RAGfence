"""Strict wire contract tests for generic HTTP responses."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from ragfence.adapters.errors import GenericHTTPParseError
from ragfence.adapters.wire import GenericHTTPAnswerResponse, GenericHTTPRetrieveResponse
from ragfence.core.models import RetrievedChunk


def _chunk() -> dict[str, object]:
    return {
        "chunk_id": str(uuid4()),
        "document_id": str(uuid4()),
        "document_title": "Security Policy",
        "chunk_index": 0,
        "content": "Approval is required.",
        "score": 0.91,
        "metadata": {"classification": "internal"},
    }


def test_retrieve_wire_model_maps_to_canonical_chunks_and_strips_extra() -> None:
    response = GenericHTTPRetrieveResponse.model_validate(
        {"chunks": [{**_chunk(), "target_debug": "must not escape"}]}
    )

    chunks = response.to_chunks()

    assert len(chunks) == 1
    assert isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].content == "Approval is required."
    assert "target_debug" not in chunks[0].model_dump()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"chunks": None},
        {"chunks": [{**_chunk(), "document_id": "not-a-uuid"}]},
        {"chunks": [{**_chunk(), "content": 123}]},
        {"chunks": ["not an object"]},
    ],
)
def test_retrieve_wire_model_rejects_malformed_payloads(payload: object) -> None:
    with pytest.raises((ValidationError, GenericHTTPParseError)):
        model = GenericHTTPRetrieveResponse.model_validate(payload)
        model.to_chunks()


def test_answer_wire_model_returns_exact_string_including_empty() -> None:
    assert GenericHTTPAnswerResponse.model_validate({"answer": ""}).to_answer() == ""
    assert (
        GenericHTTPAnswerResponse.model_validate(
            {"answer": "The policy requires approval."}
        ).to_answer()
        == "The policy requires approval."
    )


@pytest.mark.parametrize("payload", [{}, {"answer": None}, {"answer": 42}])
def test_answer_wire_model_rejects_missing_null_or_non_string(payload: object) -> None:
    with pytest.raises(ValidationError):
        GenericHTTPAnswerResponse.model_validate(payload)


def test_wire_mapping_wraps_domain_validation_as_typed_parse_error() -> None:
    payload = {"chunks": [{**_chunk(), "metadata": []}]}

    with pytest.raises((ValidationError, GenericHTTPParseError), match="metadata"):
        response = GenericHTTPRetrieveResponse.model_validate(payload)
        response.to_chunks()
