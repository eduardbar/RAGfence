from __future__ import annotations

from uuid import UUID

import pytest

from ragfence.adapters.errors import AdapterParseError, AdapterTransportError
from ragfence.adapters.mapping import (
    map_answer_response,
    map_retrieve_response,
    require_answer_path,
)

CHUNK = {
    "chunk_id": "00000000-0000-0000-0000-000000000001",
    "document_id": "00000000-0000-0000-0000-000000000002",
    "document_title": "Policy",
    "chunk_index": 2,
    "content": "Approval is required.",
    "score": 0.875,
    "metadata": {"classification": "internal", "labels": ["policy"]},
}


class StubResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: object = None,
        *,
        json_error: Exception | None = None,
    ):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_valid_retrieve_maps_to_domain_chunk_and_preserves_metadata() -> None:
    result = map_retrieve_response(StubResponse(payload={"chunks": [CHUNK]}))

    assert len(result) == 1
    assert result[0].chunk_id == UUID(CHUNK["chunk_id"])
    assert result[0].metadata == CHUNK["metadata"]


def test_valid_answer_returns_exact_string_including_empty_answer() -> None:
    assert map_answer_response(StubResponse(payload={"answer": "The answer."})) == "The answer."
    assert map_answer_response(StubResponse(payload={"answer": ""})) == ""


@pytest.mark.parametrize(
    "mapper,payload",
    [
        (map_retrieve_response, {"chunks": [CHUNK]}),
        (map_answer_response, {"answer": "ok"}),
    ],
)
def test_non_json_body_is_a_typed_parse_error(mapper, payload: object) -> None:
    with pytest.raises(AdapterParseError, match="retrieve|answer"):
        mapper(StubResponse(payload=payload, json_error=ValueError("not json")))


@pytest.mark.parametrize(
    "mapper,payload",
    [
        (map_retrieve_response, {}),
        (map_retrieve_response, {"chunks": None}),
        (map_answer_response, {}),
        (map_answer_response, {"answer": None}),
        (map_answer_response, {"answer": 1}),
    ],
)
def test_missing_null_or_wrong_required_fields_fail_closed(mapper, payload: object) -> None:
    with pytest.raises(AdapterParseError):
        mapper(StubResponse(payload=payload))


@pytest.mark.parametrize(
    "bad_chunk",
    [
        {**CHUNK, "chunk_id": "not-a-uuid"},
        {key: value for key, value in CHUNK.items() if key != "content"},
        {**CHUNK, "metadata": None},
        "not an object",
        None,
    ],
)
def test_invalid_chunk_items_never_produce_partial_success(bad_chunk: object) -> None:
    with pytest.raises(AdapterParseError, match="retrieve"):
        map_retrieve_response(StubResponse(payload={"chunks": [bad_chunk]}))


def test_non_2xx_is_a_typed_transport_error_without_body() -> None:
    with pytest.raises(AdapterTransportError, match="retrieve") as error:
        map_retrieve_response(StubResponse(status_code=502, payload={"chunks": [CHUNK]}))

    assert "Approval" not in str(error.value)


def test_extra_wire_fields_are_stripped_from_domain_models() -> None:
    result = map_retrieve_response(
        StubResponse(payload={"chunks": [{**CHUNK, "target_debug": "discard me"}], "extra": True})
    )

    assert result[0].document_title == CHUNK["document_title"]
    assert result[0].content == CHUNK["content"]
    assert result[0].metadata == CHUNK["metadata"]
    assert "target_debug" not in result[0].model_dump()


def test_optional_answer_path_fails_explicitly_but_accepts_configured_path() -> None:
    assert require_answer_path("/chat") == "/chat"
    with pytest.raises(Exception, match="answer"):
        require_answer_path(None)


def test_answer_non_2xx_is_a_typed_transport_error() -> None:
    with pytest.raises(AdapterTransportError, match="answer"):
        map_answer_response(StubResponse(status_code=404, payload={"answer": "secret body"}))
