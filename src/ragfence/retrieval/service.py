"""Secure retrieval service: authorization before retrieval (spec reqs 1-2, ADR-1/2).

The service enforces the full guard — storage row-state rules 1-3 and the pure
``decide()`` rules 4-9 — before any vector-store call. A DENY returns a typed
``SecureRetrievalResult`` with empty chunks and a trace recording zero store
calls, verifiable via a counting store double.

The target document is resolved from ``filters["document_id"]`` on the request
(``DOCUMENT_ID_FILTER``). PR 1 wires only the DENY path; the ALLOW branch (filtered
store search + citations) is added in PR 2 and is not exercised here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from ragfence.core.enums import DocumentStatus
from ragfence.core.models import (
    AuthorizationContext,
    Citation,
    DocumentPolicy,
    PolicyDecision,
    RetrievalRequest,
    RetrievedChunk,
)
from ragfence.policies.decision import decide
from ragfence.policies.guard import (
    REASON_CROSS_TENANT,
    REASON_DELETED_DOCUMENT,
    REASON_DOCUMENT_NOT_FOUND,
    REASON_DOCUMENT_NOT_READY,
    RowLoader,
)
from ragfence.retrieval.result import RetrievalDecision, SecureRetrievalResult
from ragfence.retrieval.trace import RetrievalTrace

if TYPE_CHECKING:
    from ragfence.core.protocols import VectorStore

# Request filter key carrying the UUID of the document being evaluated.
DOCUMENT_ID_FILTER = "document_id"

RowPolicyLoader = Callable[[UUID], DocumentPolicy]
DecideFn = Callable[[DocumentPolicy, AuthorizationContext], PolicyDecision]


class RetrievalService:
    """Orchestrates guard-before-retrieval over a ``VectorStore``."""

    def __init__(
        self,
        *,
        store: VectorStore,
        load_row: RowLoader,
        policy: RowPolicyLoader,
        decide_fn: DecideFn = decide,
    ) -> None:
        self._store = store
        self._load_row = load_row
        self._policy = policy
        self._decide_fn = decide_fn
        self._store_calls = 0

    def retrieve(self, request: RetrievalRequest) -> SecureRetrievalResult:
        """Run the guard before any store call; DENY short-circuits with zero store calls."""
        started = datetime.now(UTC)
        document_id = self._resolve_document_id(request)

        allowed, reasons = self._guard(document_id, request.authorization)
        decision = RetrievalDecision.ALLOW if allowed else RetrievalDecision.DENY

        chunks: list[RetrievedChunk] = []
        citations: list[Citation] = []
        if allowed:
            # PR 2: filtered store search (build_acl_predicate + top_k) and
            # citation assembly are wired here. Each store.search call increments
            # self._store_calls; the ALLOW branch is not implemented in PR 1.
            pass

        latency_ms = max(0, int((datetime.now(UTC) - started).total_seconds() * 1000))
        trace = RetrievalTrace(
            request_id=str(uuid4()),
            decision=decision,
            reasons=reasons,
            chunk_count=len(chunks),
            latency_ms=latency_ms,
            store_call_count=self._store_calls,
        )
        return SecureRetrievalResult(
            decision=decision,
            reasons=reasons,
            chunks=chunks,
            citations=citations,
            trace=trace,
        )

    def _resolve_document_id(self, request: RetrievalRequest) -> UUID:
        raw = request.filters.get(DOCUMENT_ID_FILTER)
        if raw is None:
            raise ValueError(f"request filters must include a '{DOCUMENT_ID_FILTER}'")
        return UUID(str(raw))

    def _guard(self, document_id: UUID, ctx: AuthorizationContext) -> tuple[bool, list[str]]:
        """Enforce storage rules 1-3 then policy rules 4-9, before any store call.

        Returns ``(allowed, reasons)`` where ``reasons`` name the failing rules.
        """
        row = self._load_row(document_id)
        if row is None:
            return False, [REASON_DOCUMENT_NOT_FOUND]
        if row.deleted_at is not None:
            return False, [REASON_DELETED_DOCUMENT]
        if row.status is not DocumentStatus.READY:
            return False, [REASON_DOCUMENT_NOT_READY]
        if row.tenant_id != ctx.tenant_id:
            return False, [REASON_CROSS_TENANT]

        policy = self._policy(document_id)
        decision = self._decide_fn(policy, ctx)
        return decision.allowed, decision.reasons
