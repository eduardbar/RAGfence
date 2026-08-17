"""Typed retrieval result (spec req 1, ADR-1).

A DENY is a first-class typed result carrying non-empty ``reasons`` and empty
``chunks`` — never an exception — so callers and the trace can inspect it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ragfence.core.models import Citation, RetrievedChunk

if TYPE_CHECKING:
    from ragfence.retrieval.trace import RetrievalTrace


class RetrievalDecision(StrEnum):
    """Outcome of a retrieval authorization gate."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class SecureRetrievalResult:
    """Outcome of a ``RetrievalService.retrieve`` call (ALLOW or DENY).

    A DENY result carries non-empty ``reasons``, empty ``chunks`` and empty
    ``citations``; an ALLOW result carries chunks and citations. Every result
    carries an immutable ``RetrievalTrace`` for observability.
    """

    decision: RetrievalDecision
    reasons: list[str]
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    trace: RetrievalTrace
