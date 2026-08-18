"""Persistence contracts and SQLAlchemy repositories for evaluation records.

The implementation intentionally uses only the five existing evaluation tables.
Stable UUIDs and caller-provided case IDs make replay safe without a migration;
findings are reconciled by deterministic identities and evidence is redacted
before it reaches JSONB.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol, TypeVar
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from ragfence.core.enums import ScenarioOutcome
from ragfence.db.models import (
    EvaluationCase,
    EvaluationResult,
    EvaluationRun,
    EvaluationSuite,
    RunStatus,
    SecurityFinding,
)
from ragfence.evaluation.redaction import redact_evidence as shared_redact_evidence

_NAMESPACE = UUID("7a8db6e5-8c6c-4a34-9f08-3e12f0e4d7a1")


class SuiteRepository(Protocol):
    def upsert_suite(
        self, *, name: str, description: str | None, target_adapter: str, threshold: int
    ) -> EvaluationSuite: ...


class CaseRepository(Protocol):
    def upsert_case(
        self,
        *,
        suite_id: UUID,
        case_id: UUID,
        scenario_id: str,
        prompt: str,
        actor: Mapping[str, Any],
        expected_allow: bool,
    ) -> EvaluationCase: ...


class RunRepository(Protocol):
    def upsert_run(
        self,
        *,
        suite_id: UUID,
        run_id: UUID,
        status: RunStatus,
        score: Decimal | None,
        threshold: int,
        outcome: ScenarioOutcome | None,
    ) -> EvaluationRun: ...


class ResultRepository(Protocol):
    def upsert_result(
        self,
        *,
        run_id: UUID,
        case_id: UUID,
        result_id: UUID,
        passed: bool,
        outcome: ScenarioOutcome,
        retrieved_chunk_ids: Iterable[UUID],
        answer: str | None,
        latency_ms: int,
    ) -> EvaluationResult: ...


class FindingRepository(Protocol):
    def reconcile_findings(
        self, *, run_id: UUID, findings: Iterable[Mapping[str, Any]]
    ) -> list[SecurityFinding]: ...


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def stable_suite_id(name: str, target_adapter: str) -> UUID:
    """Return the same suite identity for the same named adapter."""
    return uuid5(_NAMESPACE, f"suite:{name}:{target_adapter}")


def stable_run_id(
    suite_id: UUID, case_ids: Iterable[UUID], configuration: Mapping[str, Any]
) -> UUID:
    """Derive a replay identity from suite, stable cases, and run configuration."""
    cases = ",".join(sorted(str(case_id) for case_id in case_ids))
    return uuid5(_NAMESPACE, f"run:{suite_id}:{cases}:{_canonical(configuration)}")


def result_identity(run_id: UUID, case_id: UUID) -> UUID:
    return uuid5(_NAMESPACE, f"result:{run_id}:{case_id}")


def finding_identity(run_id: UUID, case_id: UUID | None, category: str, title: str) -> UUID:
    """Derive a stable finding key for reconciliation."""
    return uuid5(_NAMESPACE, f"finding:{run_id}:{case_id}:{category}:{title}")


def canonical_db_threshold(value: float | Decimal) -> int:
    """Round half up because the existing database threshold columns are integers."""
    threshold = Decimal(str(value))
    if not 0 <= threshold <= 100:
        raise ValueError("threshold must be between 0 and 100")
    return int(threshold.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def redact_evidence(value: Any, *, key: str | None = None) -> Any:
    """Recursively remove secrets and unrestricted content from JSONB evidence."""
    del key
    return shared_redact_evidence(value)


_ModelT = TypeVar("_ModelT")


class EvaluationRepository(
    SuiteRepository, CaseRepository, RunRepository, ResultRepository, FindingRepository
):
    """Transaction-friendly repository facade over the existing five ORM models."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def redact_evidence(value: Any) -> Any:
        return redact_evidence(value)

    def upsert_suite(
        self, *, name: str, description: str | None, target_adapter: str, threshold: int
    ) -> EvaluationSuite:
        row_id = stable_suite_id(name, target_adapter)
        row = self._session.get(EvaluationSuite, row_id)
        if row is None:
            row = EvaluationSuite(
                id=row_id,
                name=name,
                description=description,
                target_adapter=target_adapter,
                threshold=threshold,
            )
            self._session.add(row)
        else:
            row.description = description
            row.threshold = threshold
        self._session.flush()
        return row

    def upsert_case(
        self,
        *,
        suite_id: UUID,
        case_id: UUID,
        scenario_id: str,
        prompt: str,
        actor: Mapping[str, Any],
        expected_allow: bool,
    ) -> EvaluationCase:
        row = self._session.get(EvaluationCase, case_id)
        if row is not None and row.suite_id != suite_id:
            case_id = uuid5(_NAMESPACE, f"case:{suite_id}:{case_id}")
            row = self._session.get(EvaluationCase, case_id)
        payload = dict(redact_evidence(dict(actor)))
        if row is None:
            row = EvaluationCase(
                id=case_id,
                suite_id=suite_id,
                scenario_id=scenario_id,
                prompt=prompt,
                actor=payload,
                expected_allow=expected_allow,
            )
            self._session.add(row)
        else:
            row.suite_id = suite_id
            row.scenario_id = scenario_id
            row.prompt = prompt
            row.actor = payload
            row.expected_allow = expected_allow
        self._session.flush()
        return row

    def upsert_run(
        self,
        *,
        suite_id: UUID,
        run_id: UUID,
        status: RunStatus,
        score: Decimal | None,
        threshold: int,
        outcome: ScenarioOutcome | None,
    ) -> EvaluationRun:
        row = self._session.get(EvaluationRun, run_id)
        if row is None:
            row = EvaluationRun(
                id=run_id,
                suite_id=suite_id,
                status=status,
                score=score,
                threshold=threshold,
                result=outcome,
            )
            self._session.add(row)
        else:
            row.suite_id = suite_id
            row.status = status
            row.score = score
            row.threshold = threshold
            row.result = outcome
        self._session.flush()
        return row

    def upsert_result(
        self,
        *,
        run_id: UUID,
        case_id: UUID,
        result_id: UUID,
        passed: bool,
        outcome: ScenarioOutcome,
        retrieved_chunk_ids: Iterable[UUID],
        answer: str | None,
        latency_ms: int,
    ) -> EvaluationResult:
        result_id = result_identity(run_id, case_id)
        row = self._session.get(EvaluationResult, result_id)
        values = list(retrieved_chunk_ids)
        if row is None:
            row = EvaluationResult(
                id=result_id,
                run_id=run_id,
                case_id=case_id,
                passed=passed,
                outcome=outcome,
                retrieved_chunk_ids=values,
                answer=answer,
                latency_ms=latency_ms,
            )
            self._session.add(row)
        else:
            row.run_id = run_id
            row.case_id = case_id
            row.passed = passed
            row.outcome = outcome
            row.retrieved_chunk_ids = values
            row.answer = answer
            row.latency_ms = latency_ms
        self._session.flush()
        return row

    def reconcile_findings(
        self, *, run_id: UUID, findings: Iterable[Mapping[str, Any]]
    ) -> list[SecurityFinding]:
        incoming: list[SecurityFinding] = []
        for item in findings:
            case_id = item.get("case_id")
            case_uuid = UUID(str(case_id)) if case_id is not None else None
            category = str(item["category"])
            title = str(item["title"])
            row_id = UUID(str(item.get("id", finding_identity(run_id, case_uuid, category, title))))
            normalized_result_id = (
                result_identity(run_id, case_uuid)
                if case_uuid is not None
                else item.get("result_id")
            )
            row = self._session.get(SecurityFinding, row_id)
            values = {
                "result_id": normalized_result_id,
                "run_id": run_id,
                "case_id": case_uuid,
                "severity": item["severity"],
                "category": category,
                "title": title,
                "description": str(item["description"]),
                "evidence": redact_evidence(item.get("evidence", {})),
            }
            if row is None:
                row = SecurityFinding(id=row_id, **values)
                self._session.add(row)
            else:
                for name, value in values.items():
                    setattr(row, name, value)
            incoming.append(row)
        self._session.flush()
        incoming_ids = [row.id for row in incoming]
        existing = list(
            self._session.scalars(select(SecurityFinding).where(SecurityFinding.run_id == run_id))
        )
        for stale in existing:
            if stale.id not in incoming_ids:
                self._session.delete(stale)
        self._session.flush()
        return incoming

    def get_suite(self, suite_id: UUID) -> EvaluationSuite | None:
        return self._session.get(EvaluationSuite, suite_id)

    def get_case(self, case_id: UUID) -> EvaluationCase | None:
        return self._session.get(EvaluationCase, case_id)

    def get_run(self, run_id: UUID) -> EvaluationRun | None:
        return self._session.get(EvaluationRun, run_id)

    def list_results(self, run_id: UUID) -> list[EvaluationResult]:
        return list(
            self._session.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.run_id == run_id)
                .order_by(EvaluationResult.case_id)
            )
        )

    def list_findings(self, run_id: UUID) -> list[SecurityFinding]:
        return list(
            self._session.scalars(
                select(SecurityFinding)
                .where(SecurityFinding.run_id == run_id)
                .order_by(SecurityFinding.id)
            )
        )


# Explicit name for callers that prefer the implementation/protocol distinction.
SqlAlchemyEvaluationRepository = EvaluationRepository

__all__ = [
    "CaseRepository",
    "EvaluationRepository",
    "FindingRepository",
    "ResultRepository",
    "RunRepository",
    "SuiteRepository",
    "SqlAlchemyEvaluationRepository",
    "finding_identity",
    "result_identity",
    "canonical_db_threshold",
    "redact_evidence",
    "stable_run_id",
    "stable_suite_id",
]
