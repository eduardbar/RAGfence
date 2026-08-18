"""Evaluation engine/report/repository integration coverage.

The PostgreSQL path is deliberately gated by the shared Alembic fixtures.  It
uses only the five evaluation tables already present in the schema and skips
with the repository's explicit PostgreSQL-unavailable message when no DSN is
reachable.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.attacks.generators import generate_cases
from ragfence.core.enums import ScenarioOutcome
from ragfence.core.models import RetrievalRequest, RetrievedChunk
from ragfence.db.base import Base
from ragfence.db.models import (
    EvaluationCase as EvaluationCaseRow,
)
from ragfence.db.models import (
    EvaluationResult as EvaluationResultRow,
)
from ragfence.db.models import (
    EvaluationRun as EvaluationRunRow,
)
from ragfence.db.models import (
    EvaluationSuite as EvaluationSuiteRow,
)
from ragfence.db.models import (
    RunStatus,
    SecurityFinding,
)
from ragfence.evaluation.engine import EvaluationEngine
from ragfence.evaluation.report import build_report, render_json
from ragfence.evaluation.repositories import EvaluationRepository, stable_run_id


class LeakingTarget:
    """Small deterministic target that exercises retrieval and leakage findings."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                document_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                document_title="Synthetic restricted document",
                chunk_index=0,
                content="private salary content",
                score=0.99,
                metadata={"authorization": "Bearer top-secret"},
            )
        ]

    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str:
        return "The restricted salary is secret."


def _clean_schema(db_engine: Engine) -> None:
    table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with db_engine.connect() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        connection.commit()


def test_engine_report_and_replay_identity_are_composable() -> None:
    """Engine output has the shapes needed by report and replay persistence."""
    summary = EvaluationEngine(LeakingTarget(), seed=73, threshold=80).run()
    report = build_report(summary, summary.results)
    payload = json.loads(render_json(report))

    assert len(summary.results) == 10
    assert len(payload["results"]) == 10
    assert payload["score"] == summary.score
    case_ids = [result.case_id for result in summary.results]
    replay_identity = stable_run_id(
        UUID("11111111-1111-4111-8111-111111111111"), case_ids, {"seed": 73}
    )
    assert replay_identity == stable_run_id(
        UUID("11111111-1111-4111-8111-111111111111"), case_ids, {"seed": 73}
    )
    assert summary.outcome is ScenarioOutcome.CRITICAL


@pytest.mark.db
def test_generated_suite_round_trips_all_evaluation_tables(
    db_engine: Engine,
) -> None:
    """Persist and reload all ten generated cases, results, and redacted findings."""
    _clean_schema(db_engine)
    summary = EvaluationEngine(LeakingTarget(), seed=73, threshold=80).run()
    case_ids = [result.case_id for result in summary.results]

    generated_cases = {case.id: case for case in generate_cases(seed=73)}
    with Session(db_engine) as session:
        repository = EvaluationRepository(session)
        suite = repository.upsert_suite(
            name="generated-e2e",
            description="Work Unit G",
            target_adapter="leaking-test-target",
            threshold=int(summary.threshold),
        )
        for case_id, generated_case in generated_cases.items():
            repository.upsert_case(
                suite_id=suite.id,
                case_id=case_id,
                scenario_id=generated_case.scenario_id,
                prompt=generated_case.prompt,
                actor=generated_case.actor.model_dump(mode="json"),
                expected_allow=generated_case.expected_allow,
            )
        run_id = stable_run_id(suite.id, case_ids, {"seed": 73, "threshold": 80})
        run = repository.upsert_run(
            suite_id=suite.id,
            run_id=run_id,
            status=RunStatus.FAILED,
            score=Decimal(str(round(summary.score, 2))),
            threshold=int(summary.threshold),
            outcome=summary.outcome,
        )
        all_findings: list[dict[str, object]] = []
        for result in summary.results:
            repository.upsert_result(
                run_id=run.id,
                case_id=result.case_id,
                result_id=result.id,
                passed=result.passed,
                outcome=result.outcome,
                retrieved_chunk_ids=[chunk.chunk_id for chunk in result.retrieved],
                answer=result.answer,
                latency_ms=result.latency_ms,
            )
            all_findings.extend(
                {
                    "id": finding.id,
                    "result_id": result.id,
                    "case_id": result.case_id,
                    "severity": finding.severity,
                    "category": finding.category,
                    "title": finding.title,
                    "description": finding.description,
                    "evidence": finding.evidence,
                }
                for finding in result.findings
            )
        repository.reconcile_findings(run_id=run.id, findings=all_findings)
        session.commit()

        assert session.scalar(select(func.count()).select_from(EvaluationSuiteRow)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationCaseRow)) == 10
        assert session.scalar(select(func.count()).select_from(EvaluationRunRow)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationResultRow)) == 10
        finding_count = session.scalar(select(func.count()).select_from(SecurityFinding))
        assert finding_count is not None
        assert finding_count >= 10

        reloaded_run = repository.get_run(run_id)
        assert reloaded_run is not None
        assert reloaded_run.score == Decimal(str(round(summary.score, 2)))
        assert reloaded_run.result is summary.outcome
        assert len(repository.list_results(run_id)) == 10
        findings = repository.list_findings(run_id)
        assert findings
        encoded_evidence = json.dumps([finding.evidence for finding in findings])
        assert "top-secret" not in encoded_evidence
        assert "salary is secret" not in encoded_evidence

        replay_run_id = stable_run_id(suite.id, case_ids, {"seed": 73, "threshold": 80})
        assert replay_run_id == run_id
        replay_suite = repository.upsert_suite(
            name="generated-e2e",
            description="Work Unit G",
            target_adapter="leaking-test-target",
            threshold=80,
        )
        assert replay_suite.id == suite.id


@pytest.mark.db
def test_engine_persistence_replay_and_reload_g2_g4(db_engine: Engine) -> None:
    """G2-G4 exercise the engine seam, not hand-written repository calls."""
    _clean_schema(db_engine)
    engine = EvaluationEngine(LeakingTarget(), seed=74, threshold=80)
    summary = engine.run()
    with Session(db_engine) as session:
        first = engine.persist(summary, session, suite_name="engine-g2-g4")
    with Session(db_engine) as session:
        second = engine.replay(summary, session, suite_name="engine-g2-g4")
        loaded = engine.reload(session, second.run_id)
        assert first == second
        assert loaded.run.id == first.run_id
        assert len(loaded.results) == len(summary.results)
        assert loaded.findings
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(EvaluationSuiteRow)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationCaseRow)) == 10
        assert session.scalar(select(func.count()).select_from(EvaluationRunRow)) == 1
        assert session.scalar(select(func.count()).select_from(EvaluationResultRow)) == 10
        assert session.scalar(select(func.count()).select_from(SecurityFinding)) == len(
            loaded.findings
        )

    assert summary.canonical_bytes() == engine.run().canonical_bytes()
