"""Strict response contracts for generic HTTP targets."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr, ValidationError

from ragfence.core.models import RetrievedChunk

from .errors import GenericHTTPParseError


class GenericHTTPChunk(BaseModel):
    """Target chunk shape; target-specific extra fields are discarded."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: str
    document_id: str
    document_title: StrictStr
    chunk_index: StrictInt
    content: StrictStr
    score: StrictFloat
    metadata: dict[str, Any]


class GenericHTTPRetrieveResponse(BaseModel):
    """Strict envelope returned by a retrieval endpoint."""

    model_config = ConfigDict(extra="ignore")

    chunks: list[GenericHTTPChunk]

    def to_chunks(self) -> list[RetrievedChunk]:
        """Convert the target envelope to canonical domain chunks."""
        try:
            return [RetrievedChunk.model_validate(chunk.model_dump()) for chunk in self.chunks]
        except ValidationError as exc:
            raise GenericHTTPParseError("retrieve", "invalid retrieve response") from exc


class GenericHTTPAnswerResponse(BaseModel):
    """Strict envelope returned by an answer endpoint."""

    model_config = ConfigDict(extra="ignore")

    answer: StrictStr

    def to_answer(self) -> str:
        """Return the validated answer without coercion or decoration."""
        return self.answer


# Short aliases keep call sites readable while retaining explicit public names.
RetrieveResponse = GenericHTTPRetrieveResponse
AnswerResponse = GenericHTTPAnswerResponse
