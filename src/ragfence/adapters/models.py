"""Strict wire contracts for generic HTTP target responses."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, StrictStr


class RetrievedChunkResponse(BaseModel):
    """One target chunk; target-only fields are intentionally discarded."""

    model_config = ConfigDict(extra="ignore")

    chunk_id: UUID
    document_id: UUID
    document_title: StrictStr
    chunk_index: StrictInt
    content: StrictStr
    score: StrictFloat
    metadata: dict[str, Any]


class RetrieveResponse(BaseModel):
    """Strict retrieve response envelope."""

    model_config = ConfigDict(extra="ignore")

    chunks: list[RetrievedChunkResponse]


class AnswerResponse(BaseModel):
    """Strict answer response envelope; an explicitly empty answer is valid."""

    model_config = ConfigDict(extra="ignore")

    answer: StrictStr
