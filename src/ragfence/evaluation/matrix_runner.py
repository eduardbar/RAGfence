"""Declarative control matrix execution engine (spec R2, R3).

Executes evaluation controls against a target in declared order, producing
typed observations and results. The matrix owns stable control execution
semantics; gate scoring and decision logic remain in gate.py.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from ragfence.attacks.generators import EvaluationControl, ExpectedBehavior
from ragfence.core.models import RetrievalRequest
from ragfence.datasets.acme import build_acme_corp
from ragfence.evaluation.redaction import bounded_text


class ControlStatus(StrEnum):
    """Typed control execution outcomes (spec R3)."""

    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ControlObservation:
    """Raw execution evidence from one control run."""

    control_id: str
    retrieved_count: int
    answer: str | None
    error: str | None
    latency_ms: int
    identity_represented: bool
    evidence_present: bool
    retrieved_document_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class ControlResult:
    """One control execution result with status and reason."""

    control: EvaluationControl
    status: str
    reason: str
    observation: ControlObservation


@runtime_checkable
class MatrixTarget(Protocol):
    """Target protocol for matrix execution."""

    def retrieve(self, request: RetrievalRequest) -> object: ...


def _resolve_document_id(target_document: str) -> UUID:
    """Resolve the fixture document UUID from the acme corpus."""
    acme = build_acme_corp()
    if target_document not in acme.documents:
        raise ValueError(f"target document not found in fixture: {target_document}")
    return acme.documents[target_document].id


def _build_request(control: EvaluationControl) -> RetrievalRequest:
    """Build a RetrievalRequest from a control's declarative fields."""
    from ragfence.datasets.acme import build_acme_corp, build_globex_corp

    acme = build_acme_corp()
    globex = build_globex_corp()
    dataset = globex if control.actor_tenant == "globex-corp" else acme

    if control.actor_email not in dataset.users:
        raise ValueError(f"actor not found in tenant: {control.actor_email}")

    authorization = dataset.context_for(control.actor_email)
    document_id = _resolve_document_id(control.target_document)

    return RetrievalRequest(
        query=control.prompt,
        authorization=authorization,
        top_k=10,
        filters={"document_id": document_id},
    )


def run_matrix(
    target: MatrixTarget,
    controls: tuple[EvaluationControl, ...],
    *,
    identity_represented: bool = True,
    identity_represented_for: Callable[[EvaluationControl], bool] | None = None,
    skip_non_required: bool = False,
) -> tuple[ControlResult, ...]:
    """Execute controls in declared order against the target.

    Verdict semantics:
    - execution raises -> INCONCLUSIVE, reason "target error: ..."
    - control.identity_required and not identity_represented -> INCONCLUSIVE
    - expected MUST_ALLOW: retrieved_count >= 1 -> PASS; == 0 -> FAIL
    - expected MUST_BLOCK: retrieved_count == 0 -> PASS; >= 1 -> FAIL
    - SKIPPED only when skip_non_required and not control.required_for_gate

    ``identity_represented`` is the legacy global flag (default True, preserves
    the DB reference target behaviour). ``identity_represented_for`` is an
    optional per-control hook (spec R4.2): when provided it takes precedence
    over the global flag and is called for every control to decide whether
    identity is represented for that specific case.

    Soft-delete precondition: the soft-deleted-document control requires the
    target document to be soft-deleted. If the target has a materialize_precondition
    method, it is called before execution and cleanup is called after.
    """
    results: list[ControlResult] = []

    for control in controls:
        if identity_represented_for is not None:
            control_identity_represented = identity_represented_for(control)
        else:
            control_identity_represented = identity_represented

        if skip_non_required and not control.required_for_gate:
            observation = ControlObservation(
                control_id=control.id,
                retrieved_count=0,
                answer=None,
                error=None,
                latency_ms=0,
                identity_represented=control_identity_represented,
                evidence_present=False,
            )
            results.append(
                ControlResult(
                    control=control,
                    status=ControlStatus.SKIPPED,
                    reason="non-required control skipped",
                    observation=observation,
                )
            )
            continue

        if control.identity_required and not control_identity_represented:
            observation = ControlObservation(
                control_id=control.id,
                retrieved_count=0,
                answer=None,
                error=None,
                latency_ms=0,
                identity_represented=False,
                evidence_present=False,
            )
            results.append(
                ControlResult(
                    control=control,
                    status=ControlStatus.INCONCLUSIVE,
                    reason="identity not represented",
                    observation=observation,
                )
            )
            continue

        precondition_cleanup = None
        if control.category == "soft-deletion" and hasattr(target, "materialize_precondition"):
            try:
                precondition_cleanup = target.materialize_precondition(control)
            except Exception as exc:
                observation = ControlObservation(
                    control_id=control.id,
                    retrieved_count=0,
                    answer=None,
                    error=bounded_text(str(exc), max_length=200),
                    latency_ms=0,
                    identity_represented=control_identity_represented,
                    evidence_present=False,
                )
                results.append(
                    ControlResult(
                        control=control,
                        status=ControlStatus.INCONCLUSIVE,
                        reason=f"precondition error: {bounded_text(str(exc), max_length=100)}",
                        observation=observation,
                    )
                )
                continue

        started = time.time()
        cleanup_error = None
        try:
            request = _build_request(control)
            raw_result = target.retrieve(request)
            if hasattr(raw_result, "chunks"):
                retrieved_list = list(raw_result.chunks)
            elif isinstance(raw_result, list):
                retrieved_list = raw_result
            else:
                retrieved_list = list(raw_result)  # type: ignore[call-overload]
            retrieved_count = len(retrieved_list)
            retrieved_document_ids = tuple(
                UUID(str(chunk.document_id))
                for chunk in retrieved_list
                if hasattr(chunk, "document_id")
            )
            answer = None
            if hasattr(target, "answer"):
                answer = target.answer(request, retrieved_list)
            error = None
            evidence_present = retrieved_count > 0
        except Exception as exc:
            latency_ms = max(0, int((time.time() - started) * 1000))
            observation = ControlObservation(
                control_id=control.id,
                retrieved_count=0,
                answer=None,
                error=bounded_text(str(exc), max_length=200),
                latency_ms=latency_ms,
                identity_represented=control_identity_represented,
                evidence_present=False,
                retrieved_document_ids=(),
            )
            results.append(
                ControlResult(
                    control=control,
                    status=ControlStatus.INCONCLUSIVE,
                    reason=f"target error: {bounded_text(str(exc), max_length=100)}",
                    observation=observation,
                )
            )
            if precondition_cleanup is not None:
                try:
                    precondition_cleanup()
                except Exception:
                    pass
            continue

        if precondition_cleanup is not None:
            try:
                precondition_cleanup()
            except Exception as cleanup_exc:
                cleanup_error = cleanup_exc

        latency_ms = max(0, int((time.time() - started) * 1000))

        if cleanup_error is not None:
            observation = ControlObservation(
                control_id=control.id,
                retrieved_count=retrieved_count,
                answer=answer,
                error=bounded_text(str(cleanup_error), max_length=200),
                latency_ms=latency_ms,
                identity_represented=control_identity_represented,
                evidence_present=False,
                retrieved_document_ids=retrieved_document_ids,
            )
            results.append(
                ControlResult(
                    control=control,
                    status=ControlStatus.INCONCLUSIVE,
                    reason=(
                        f"postcondition restoration failed: "
                        f"{bounded_text(str(cleanup_error), max_length=100)}"
                    ),
                    observation=observation,
                )
            )
            continue

        target_document_uuid = _resolve_document_id(control.target_document)

        if control.expected_behavior == ExpectedBehavior.MUST_ALLOW:
            if retrieved_count == 0:
                status = ControlStatus.FAIL
                reason = "required allow returned zero chunks"
            elif (
                control.retrieval_evidence_required
                and target_document_uuid not in retrieved_document_ids
            ):
                status = ControlStatus.FAIL
                reason = "required allow returned no chunk from target document"
            else:
                status = ControlStatus.PASS
                reason = "authorized retrieval returned chunks"
        else:
            if retrieved_count == 0:
                status = ControlStatus.PASS
                reason = "unauthorized retrieval blocked"
            else:
                status = ControlStatus.FAIL
                reason = f"unauthorized retrieval: {retrieved_count} chunks"

        observation = ControlObservation(
            control_id=control.id,
            retrieved_count=retrieved_count,
            answer=answer,
            error=error,
            latency_ms=latency_ms,
            identity_represented=control_identity_represented,
            evidence_present=evidence_present,
            retrieved_document_ids=retrieved_document_ids,
        )
        results.append(
            ControlResult(
                control=control,
                status=status,
                reason=reason,
                observation=observation,
            )
        )

    return tuple(results)
