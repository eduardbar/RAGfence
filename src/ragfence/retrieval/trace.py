"""Immutable retrieval trace for observability (spec req 5, ADR-6).

Records ``request_id``, ``decision``, ``reasons``, chunk count, latency and the
number of vector-store calls. It never carries full document contents or
secrets, keeping the trace safe to log by default.
"""

from __future__ import annotations

from dataclasses import dataclass

from ragfence.retrieval.result import RetrievalDecision


@dataclass(frozen=True)
class RetrievalTrace:
    """Immutable, observability-safe summary of a single ``retrieve`` call."""

    request_id: str
    decision: RetrievalDecision
    reasons: list[str]
    chunk_count: int
    latency_ms: int
    store_call_count: int
