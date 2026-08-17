"""Secure retrieval service: authorization before retrieval (spec reqs 1-5, ADR-1/2/3).

The service enforces the full guard — storage row-state rules 1-3 and the pure
``decide()`` rules 4-9 — before any vector-store call. A DENY returns a typed
``SecureRetrievalResult`` with empty chunks and a trace recording zero store
calls, verifiable via a counting store double.

The target document is resolved from ``filters["document_id"]`` on the request
(``DOCUMENT_ID_FILTER``). On ALLOW the service performs a corpus-wide filtered
search: it embeds the query, builds the ACL predicate from typed columns only
(``build_acl_predicate``, never the JSONB ``metadata`` column) and passes it as a
single pre-filter statement to ``VectorStore.search``, then assembles citations.
The predicate is the per-row authorization gate — there is no post-hoc filtering.
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
from ragfence.db.models import DocumentACL
from ragfence.db.repositories import build_acl_predicate
from ragfence.policies.decision import decide
from ragfence.policies.guard import (
    REASON_CROSS_TENANT,
    REASON_DELETED_DOCUMENT,
    REASON_DOCUMENT_NOT_FOUND,
    REASON_DOCUMENT_NOT_READY,
    RowLoader,
)
from ragfence.providers.fakes import FakeEmbeddingProvider
from ragfence.retrieval.citations import DocumentMetaLoader, build_citations
from ragfence.retrieval.result import RetrievalDecision, SecureRetrievalResult
from ragfence.retrieval.trace import RetrievalTrace

if TYPE_CHECKING:
    from ragfence.core.protocols import VectorStore

# Request filter key carrying the UUID of the document being evaluated.
DOCUMENT_ID_FILTER = "document_id"

RowPolicyLoader = Callable[[UUID], DocumentPolicy]
DecideFn = Callable[[DocumentPolicy, AuthorizationContext], PolicyDecision]
EmbedFn = Callable[[str], list[float]]


class RetrievalService:
    """Orchestrates guard-before-retrieval over a ``VectorStore``."""

    def __init__(
        self,
        *,
        store: VectorStore,
        load_row: RowLoader,
        policy: RowPolicyLoader,
        decide_fn: DecideFn = decide,
        embed: EmbedFn | None = None,
        document_meta: DocumentMetaLoader | None = None,
    ) -> None:
        self._store = store
        self._load_row = load_row
        self._policy = policy
        self._decide_fn = decide_fn
        # Deterministic zero-I/O embedding default (TRD §8); inject to override.
        _embedder = FakeEmbeddingProvider()
        self._embed = embed or (lambda text: _embedder.embed([text])[0])
        self._document_meta = document_meta or (lambda _did: None)
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
            # Corpus-wide filtered search: one pre-filter statement built from typed
            # ACL columns only (never JSONB metadata); the predicate is the gate.
            predicate = build_acl_predicate(DocumentACL, request.authorization)
            embedding = self._embed(request.query)
            chunks = self._store.search(
                embedding=embedding,
                policy_predicate=predicate,
                top_k=request.top_k,
            )
            self._store_calls += 1
            citations = build_citations(chunks, self._document_meta)

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
