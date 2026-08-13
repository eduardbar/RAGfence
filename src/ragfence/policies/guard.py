"""Authorization-before-retrieval guard (TRD §4.3, §5.3).

Thin orchestration seam: consumes storage-layer row state (rules 1-3) and the
pure decision (rules 4-9) so a DENY never reaches the retrieval layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ragfence.core.enums import DocumentStatus
from ragfence.core.models import (
    AuthorizationContext,
    DocumentPolicy,
    PolicyDecision,
    RetrievedChunk,
)
from ragfence.policies.decision import decide

REASON_DELETED_DOCUMENT = "deleted_document"
REASON_DOCUMENT_NOT_READY = "document_not_ready"
REASON_CROSS_TENANT = "cross_tenant"
REASON_DOCUMENT_NOT_FOUND = "document_not_found"


@dataclass(frozen=True)
class DocumentRowState:
    """Storage-layer facts for rules 1-3, resolved before any retrieval."""

    document_id: UUID
    tenant_id: UUID
    status: DocumentStatus
    deleted_at: datetime | None


@dataclass(frozen=True)
class GuardedResult:
    decision: PolicyDecision
    chunks: list[RetrievedChunk]


RowLoader = Callable[[UUID], DocumentRowState | None]
Retriever = Callable[[], list[RetrievedChunk]]


def _deny(reason: str, evaluated_at: datetime) -> PolicyDecision:
    return PolicyDecision(allowed=False, reasons=[reason], evaluated_at=evaluated_at)


def guard_retrieval(
    *,
    document_id: UUID,
    policy: DocumentPolicy,
    ctx: AuthorizationContext,
    load_row: RowLoader,
    retrieve: Retriever,
) -> GuardedResult:
    """Enforce rules 1-9 before delegating to ``retrieve``; a DENY never retrieves.

    Rules 1-3 consume the persisted row (deleted_at, status, tenant); rules 4-9
    run the pure decision. Only an allowed decision reaches ``retrieve``.
    """
    evaluated_at = datetime.now(UTC)
    row = load_row(document_id)
    if row is None:
        return GuardedResult(decision=_deny(REASON_DOCUMENT_NOT_FOUND, evaluated_at), chunks=[])
    if row.deleted_at is not None:
        return GuardedResult(decision=_deny(REASON_DELETED_DOCUMENT, evaluated_at), chunks=[])
    if row.status is not DocumentStatus.READY:
        return GuardedResult(decision=_deny(REASON_DOCUMENT_NOT_READY, evaluated_at), chunks=[])
    if row.tenant_id != ctx.tenant_id:
        return GuardedResult(decision=_deny(REASON_CROSS_TENANT, evaluated_at), chunks=[])

    decision = decide(policy, ctx)
    if not decision.allowed:
        return GuardedResult(decision=decision, chunks=[])
    return GuardedResult(decision=decision, chunks=retrieve())
