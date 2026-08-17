"""Secure retrieval service tests (spec reqs 1-5; PR 1 DENY + PR 2 ALLOW).

Spec reference: openspec/changes/ragfence-secure-retrieval/specs/secure-retrieval/spec.md
- Requirement: Deny is a typed result (typed DENY, non-empty reasons, empty chunks, no exception)
- Requirement: Authorization Before Retrieval (DENY => zero vector-store calls, via counting double)
- Requirement: Filtered Vector Retrieval (ALLOW => predicate + top_k; spoofing no-op)
- Requirement: Citation Provenance (one Citation per chunk, title/source/checksum/chunk_index/score)
- Requirement: Retrieval Trace (decision, reasons, chunk count, latency; no content/secrets)

The service must resolve the target document from ``filters["document_id"]`` and
run the row-state guard (rules 1-3) plus ``decide()`` (rules 4-9) before any
store call. On ALLOW it searches the store with ``build_acl_predicate`` (typed
columns only — the corpus-wide authorization gate) and assembles citations.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.dialects import postgresql

from ragfence.core.enums import DocumentStatus
from ragfence.core.models import RetrievalRequest, RetrievedChunk
from ragfence.datasets.acme import AcmeDocument, build_acme_corp
from ragfence.db.models import DocumentACL
from ragfence.policies.decision import REASON_CLASSIFICATION_ESCALATION
from ragfence.policies.guard import (
    REASON_DELETED_DOCUMENT,
    DocumentRowState,
)
from ragfence.providers.fakes import FakeEmbeddingProvider
from ragfence.retrieval.result import RetrievalDecision, SecureRetrievalResult
from ragfence.retrieval.service import DOCUMENT_ID_FILTER, RetrievalService
from ragfence.retrieval.trace import RetrievalTrace
from tests.support.vector_store import CountingVectorStore


def _row_state(doc: object) -> DocumentRowState:
    return DocumentRowState(
        document_id=doc.id,
        tenant_id=doc.tenant_id,
        status=doc.status,
        deleted_at=None,
    )


def _make_service(acme, store: CountingVectorStore) -> RetrievalService:
    """Service serving every Acme document by id (row loader + policy resolution)."""
    by_id: dict[UUID, object] = {d.id: d for d in acme.documents.values()}
    return RetrievalService(
        store=store,
        load_row=lambda did: _row_state(by_id[did]) if did in by_id else None,
        policy=lambda did: by_id[did].policy,
        document_meta=lambda did: by_id[did] if did in by_id else None,
    )


def _embed(text: str) -> list[float]:
    return FakeEmbeddingProvider().embed([text])[0]


def _chunk_for(doc: AcmeDocument, *, index: int = 0, content: str | None = None) -> RetrievedChunk:
    """Build a RetrievedChunk for an Acme document (source/checksum on the doc row)."""
    return RetrievedChunk(
        chunk_id=UUID(int=doc.id.int + index + 1),
        document_id=doc.id,
        document_title=doc.title,
        chunk_index=index,
        content=content or doc.body,
        score=1.0 - index * 0.1,
        metadata={},
    )


def _compiled_predicate(predicate: Any) -> str:
    """Compile the captured SQL predicate to PostgreSQL, with no DB connection."""
    from sqlalchemy import select

    stmt = select(DocumentACL).where(predicate)
    return str(stmt.compile(dialect=postgresql.dialect()))


def _request(acme, ctx, document, *, top_k: int = 3) -> RetrievalRequest:
    return RetrievalRequest(
        query="retrieval test",
        authorization=ctx,
        top_k=top_k,
        filters={DOCUMENT_ID_FILTER: str(document.id)},
    )


def test_engineering_user_deny_on_cfo_pdf_with_zero_store_calls() -> None:
    """Spec scenario: internal engineering user vs confidential CFO.pdf => DENY, 0 searches."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("engineering_employee@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]

    result: SecureRetrievalResult = _make_service(acme, store).retrieve(_request(acme, ctx, cfo))

    assert result.decision == RetrievalDecision.DENY
    assert result.reasons == [REASON_CLASSIFICATION_ESCALATION]
    assert result.chunks == []
    assert result.citations == []
    assert store.search_calls == 0
    assert result.trace.store_call_count == 0
    assert result.trace.decision == RetrievalDecision.DENY
    assert result.trace.chunk_count == 0


def test_confidential_finance_user_deny_on_board_plan_with_zero_store_calls() -> None:
    """Spec scenario: non-executive confidential user vs restricted board-plan => DENY."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    board = acme.documents["executive/strategy/2026-board-plan.pdf"]

    result: SecureRetrievalResult = _make_service(acme, store).retrieve(_request(acme, ctx, board))

    assert result.decision == RetrievalDecision.DENY
    assert result.reasons == [REASON_CLASSIFICATION_ESCALATION]
    assert result.chunks == []
    assert result.citations == []
    assert store.search_calls == 0
    assert result.trace.store_call_count == 0


def test_deleted_document_deny_before_any_store_call() -> None:
    """Triangulation: row-state rule (deleted) denies before decide/store, different code path."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]
    deleted_row = DocumentRowState(
        document_id=cfo.id,
        tenant_id=acme.tenant.id,
        status=DocumentStatus.READY,
        deleted_at=datetime.now(UTC),
    )
    service = RetrievalService(
        store=store,
        load_row=lambda _: deleted_row,
        policy=lambda _: cfo.policy,
    )

    result: SecureRetrievalResult = service.retrieve(_request(acme, ctx, cfo))

    assert result.decision == RetrievalDecision.DENY
    assert result.reasons == [REASON_DELETED_DOCUMENT]
    assert result.chunks == []
    assert store.search_calls == 0
    assert result.trace.store_call_count == 0


def test_retrieval_trace_is_immutable() -> None:
    """Trace is a frozen typed record (ADR-6); mutation raises FrozenInstanceError."""
    trace = RetrievalTrace(
        request_id="request-1",
        decision=RetrievalDecision.DENY,
        reasons=[REASON_CLASSIFICATION_ESCALATION],
        chunk_count=0,
        latency_ms=1,
        store_call_count=0,
    )
    assert trace.request_id == "request-1"
    assert trace.decision == RetrievalDecision.DENY
    assert trace.reasons == [REASON_CLASSIFICATION_ESCALATION]
    assert trace.chunk_count == 0
    assert trace.latency_ms == 1
    assert trace.store_call_count == 0
    with pytest.raises(FrozenInstanceError):
        trace.chunk_count = 5


# --- PR 2: ALLOW path (spec reqs 3-5) ---


def test_same_department_allow_returns_allowed_chunks_with_predicate() -> None:
    """Spec: same-department ALLOW returns <= top_k chunks; predicate passed down."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]
    store.add(_chunk_for(cfo), _embed("retrieval test"))

    result: SecureRetrievalResult = _make_service(acme, store).retrieve(
        _request(acme, ctx, cfo, top_k=3)
    )

    assert result.decision == RetrievalDecision.ALLOW
    assert result.reasons == []
    assert len(result.chunks) <= 3
    assert len(result.chunks) == 1
    assert result.chunks[0].document_id == cfo.id
    # The store search ran exactly once with the ACL predicate (corpus-wide gate).
    assert store.search_calls == 1
    assert store.last_predicate is not None
    sql = _compiled_predicate(store.last_predicate)
    assert "document_acl.tenant_id" in sql
    assert "document_acl.classification" in sql
    assert "metadata" not in sql


def test_allow_predicate_references_typed_columns_only_never_metadata() -> None:
    """Spec req 3: the predicate references typed columns only, never JSONB metadata."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]
    store.add(_chunk_for(cfo), _embed("retrieval test"))

    _make_service(acme, store).retrieve(_request(acme, ctx, cfo))

    sql = _compiled_predicate(store.last_predicate)
    assert "metadata" not in sql
    assert "document_acl.tenant_id" in sql
    assert "document_acl.allowed_user_ids" in sql
    assert "document_acl.department_id" in sql


def test_metadata_spoofing_is_a_no_op() -> None:
    """Spec: modified JSONB metadata granting broader access leaves the result unchanged."""
    acme = build_acme_corp()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]

    normal_store = CountingVectorStore()
    normal_store.add(_chunk_for(cfo), _embed("retrieval test"))
    normal = _make_service(acme, normal_store).retrieve(_request(acme, ctx, cfo))

    spoofed_store = CountingVectorStore()
    spoofed_chunk = _chunk_for(cfo)
    spoofed_chunk.metadata = {"classification": "restricted", "department": "executive"}
    spoofed_store.add(spoofed_chunk, _embed("retrieval test"))
    spoofed = _make_service(acme, spoofed_store).retrieve(_request(acme, ctx, cfo))

    assert spoofed.decision == normal.decision == RetrievalDecision.ALLOW
    assert [c.chunk_id for c in spoofed.chunks] == [c.chunk_id for c in normal.chunks]
    # The predicate never consults the JSONB metadata column.
    assert "metadata" not in _compiled_predicate(spoofed_store.last_predicate)


def test_citations_carry_provenance_and_truncate_snippet() -> None:
    """Spec req 4: one Citation per chunk with provenance; snippet truncated."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]
    store.add(_chunk_for(cfo), _embed("retrieval test"))

    result: SecureRetrievalResult = _make_service(acme, store).retrieve(_request(acme, ctx, cfo))

    assert len(result.citations) == len(result.chunks) == 1
    citation = result.citations[0]
    assert citation.document_id == cfo.id
    assert citation.document_title == cfo.title
    assert citation.source == cfo.source
    assert citation.checksum == cfo.checksum
    assert citation.chunk_index == 0
    assert citation.score == result.chunks[0].score
    # Snippet is truncated relative to the full chunk content (redaction).
    assert len(citation.snippet) <= 200
    assert len(citation.snippet) < len(result.chunks[0].content)


def test_allow_trace_records_decision_reasons_count_and_no_content() -> None:
    """Spec req 5: trace records decision/reasons/chunk count/store calls; no content/secrets."""
    acme = build_acme_corp()
    store = CountingVectorStore()
    ctx = acme.context_for("finance_analyst@acme-corp.example")
    cfo = acme.documents["finance/payroll/cfo-payroll-summary.pdf"]
    store.add(_chunk_for(cfo), _embed("retrieval test"))

    result: SecureRetrievalResult = _make_service(acme, store).retrieve(_request(acme, ctx, cfo))

    trace = result.trace
    assert trace.decision == RetrievalDecision.ALLOW
    assert trace.reasons == []
    assert trace.chunk_count == 1
    assert trace.store_call_count == 1
    assert trace.request_id  # non-empty opaque id
    assert trace.latency_ms >= 0
    # No full document content or secret leaks into the trace.
    assert cfo.body not in trace.reasons
    assert "password" not in str(trace.reasons)
