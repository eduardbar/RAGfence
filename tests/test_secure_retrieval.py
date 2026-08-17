"""Secure retrieval service tests (spec reqs 1-2; PR 1 DENY foundation).

Spec reference: openspec/changes/ragfence-secure-retrieval/specs/secure-retrieval/spec.md
- Requirement: Deny is a typed result (typed DENY, non-empty reasons, empty chunks, no exception)
- Requirement: Authorization Before Retrieval (DENY => zero vector-store calls, via counting double)

PR 1 wires only the DENY path; the ALLOW path is PR 2. The service must resolve
the target document from ``filters["document_id"]`` and run the row-state guard
(rules 1-3) plus ``decide()`` (rules 4-9) before any store call.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest

from ragfence.core.enums import DocumentStatus
from ragfence.core.models import RetrievalRequest
from ragfence.datasets.acme import build_acme_corp
from ragfence.policies.decision import REASON_CLASSIFICATION_ESCALATION
from ragfence.policies.guard import (
    REASON_DELETED_DOCUMENT,
    DocumentRowState,
)
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
    )


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
