"""Authorization-before-retrieval guard tests (task 3.2).

Spec reference: openspec/changes/ragfence-foundation/specs/policy-engine/spec.md
- Authorization Before Retrieval / Scenario: Denied request never retrieves
- TRD §5.3 rules 1-3: deleted_at, status READY, tenant match
"""

import uuid
from datetime import UTC, datetime

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.core.models import AuthorizationContext, DocumentPolicy, RetrievedChunk
from ragfence.policies.guard import DocumentRowState, guard_retrieval

TENANT = uuid.uuid4()
DOCUMENT = uuid.uuid4()


def _ctx(*, department_id=None) -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=TENANT,
        user_id=uuid.uuid4(),
        department_id=department_id,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )


def _policy(*, department_id=None) -> DocumentPolicy:
    return DocumentPolicy(
        classification=Classification.INTERNAL,
        department_id=department_id,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
    )


def _ready_row() -> DocumentRowState:
    return DocumentRowState(
        document_id=DOCUMENT, tenant_id=TENANT, status=DocumentStatus.READY, deleted_at=None
    )


def test_denied_request_never_retrieves() -> None:
    """Spec scenario: a DENY prevents any retrieval call entirely."""
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return []

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=None),
        ctx=_ctx(department_id=uuid.uuid4()),
        load_row=lambda _: _ready_row(),
        retrieve=_retrieve,
    )
    assert result.decision.allowed is False
    assert result.decision.reasons == ["no_implicit_department_access"]
    assert result.chunks == []
    assert calls == []


def test_deleted_document_denied_without_retrieval() -> None:
    row = DocumentRowState(
        document_id=DOCUMENT,
        tenant_id=TENANT,
        status=DocumentStatus.READY,
        deleted_at=datetime.now(UTC),
    )
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return []

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=uuid.uuid4()),
        ctx=_ctx(department_id=uuid.uuid4()),
        load_row=lambda _: row,
        retrieve=_retrieve,
    )
    assert result.decision.allowed is False
    assert result.decision.reasons == ["deleted_document"]
    assert calls == []


def test_not_ready_document_denied_without_retrieval() -> None:
    row = DocumentRowState(
        document_id=DOCUMENT, tenant_id=TENANT, status=DocumentStatus.PENDING, deleted_at=None
    )
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return []

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=uuid.uuid4()),
        ctx=_ctx(department_id=uuid.uuid4()),
        load_row=lambda _: row,
        retrieve=_retrieve,
    )
    assert result.decision.allowed is False
    assert result.decision.reasons == ["document_not_ready"]
    assert calls == []


def test_cross_tenant_document_denied_without_retrieval() -> None:
    row = DocumentRowState(
        document_id=DOCUMENT, tenant_id=uuid.uuid4(), status=DocumentStatus.READY, deleted_at=None
    )
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return []

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=uuid.uuid4()),
        ctx=_ctx(department_id=uuid.uuid4()),
        load_row=lambda _: row,
        retrieve=_retrieve,
    )
    assert result.decision.allowed is False
    assert result.decision.reasons == ["cross_tenant"]
    assert calls == []


def test_missing_row_denied_without_retrieval() -> None:
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return []

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=uuid.uuid4()),
        ctx=_ctx(department_id=uuid.uuid4()),
        load_row=lambda _: None,
        retrieve=_retrieve,
    )
    assert result.decision.allowed is False
    assert result.decision.reasons == ["document_not_found"]
    assert calls == []


def test_allowed_request_retrieves() -> None:
    dept = uuid.uuid4()
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=DOCUMENT,
        document_title="CFO Memo",
        chunk_index=0,
        content="confidential",
        score=0.9,
        metadata={},
    )
    calls: list[str] = []

    def _retrieve() -> list[RetrievedChunk]:
        calls.append("retrieve")
        return [chunk]

    result = guard_retrieval(
        document_id=DOCUMENT,
        policy=_policy(department_id=dept),
        ctx=_ctx(department_id=dept),
        load_row=lambda _: _ready_row(),
        retrieve=_retrieve,
    )
    assert result.decision.allowed is True
    assert result.chunks == [chunk]
    assert calls == ["retrieve"]
