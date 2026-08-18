"""Strict response decoding and conversion to canonical domain models."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from ragfence.adapters.errors import (
    AdapterParseError,
    AdapterTransportError,
    GenericHTTPParseError,
    UnsupportedOperationError,
)
from ragfence.adapters.wire import GenericHTTPAnswerResponse, GenericHTTPRetrieveResponse
from ragfence.core.models import RetrievedChunk


class _Response(Protocol):
    status_code: int

    def json(self) -> object: ...


def _payload(response: _Response, operation: str) -> object:
    if not 200 <= response.status_code < 300:
        raise AdapterTransportError(operation, response.status_code)
    try:
        return response.json()
    except (TypeError, ValueError, UnicodeError):
        raise AdapterParseError(operation, "response body is not JSON") from None


def map_retrieve_response(response: _Response) -> list[RetrievedChunk]:
    """Validate a retrieve response fully, then map every chunk atomically."""

    payload = _payload(response, "retrieve")
    try:
        parsed = GenericHTTPRetrieveResponse.model_validate(payload)
        return parsed.to_chunks()
    except (ValidationError, GenericHTTPParseError):
        raise AdapterParseError(
            "retrieve", "response does not match the retrieve contract"
        ) from None


def map_answer_response(response: _Response) -> str:
    """Validate an answer response and return only its canonical string."""

    payload = _payload(response, "answer")
    try:
        return GenericHTTPAnswerResponse.model_validate(payload).to_answer()
    except ValidationError:
        raise AdapterParseError("answer", "response does not match the answer contract") from None


def require_answer_path(answer_path: str | None) -> str:
    """Return a configured answer path or fail explicitly for retrieval-only mode."""

    if answer_path is None:
        raise UnsupportedOperationError("answer")
    return answer_path


# Verb-named aliases make the mapping seam convenient for transport adapters.
parse_retrieve_response = map_retrieve_response
parse_answer_response = map_answer_response
