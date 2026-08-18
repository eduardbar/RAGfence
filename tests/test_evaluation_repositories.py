from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from ragfence.core.enums import FindingSeverity, ScenarioOutcome
from ragfence.db.models import RunStatus
from ragfence.evaluation.repositories import (
    EvaluationRepository,
    canonical_db_threshold,
    finding_identity,
    stable_run_id,
    stable_suite_id,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
SUITE = UUID("22222222-2222-4222-8222-222222222222")
CASE = UUID("33333333-3333-4333-8333-333333333333")
RUN = UUID("44444444-4444-4444-8444-444444444444")
RESULT = UUID("55555555-5555-4555-8555-555555555555")


def test_stable_identities_are_reproducible() -> None:
    assert stable_suite_id("ci", "reference") == stable_suite_id("ci", "reference")
    assert stable_run_id(SUITE, [CASE], {"score": 80}) == stable_run_id(
        SUITE, [CASE], {"score": 80}
    )
    assert finding_identity(RUN, CASE, "unauthorized-retrieval", "Leak") == finding_identity(
        RUN, CASE, "unauthorized-retrieval", "Leak"
    )


def test_finding_identity_changes_for_distinct_findings() -> None:
    assert finding_identity(RUN, CASE, "a", "title") != finding_identity(RUN, CASE, "b", "title")


def test_result_and_finding_identities_include_run_identity() -> None:
    from ragfence.evaluation.repositories import result_identity

    other_run = UUID("77777777-7777-4777-8777-777777777777")
    assert result_identity(RUN, CASE) != result_identity(other_run, CASE)
    assert finding_identity(RUN, CASE, "a", "title") != finding_identity(
        other_run, CASE, "a", "title"
    )


def test_integer_database_threshold_uses_explicit_half_up_policy() -> None:
    assert canonical_db_threshold(80.4) == 80
    assert canonical_db_threshold(80.5) == 81
    assert canonical_db_threshold(80.75) == 81


def test_repository_protocol_is_implemented() -> None:
    assert isinstance(EvaluationRepository, type)


def test_redact_evidence_before_persistence() -> None:
    evidence = {
        "authorization": "Bearer super-secret",
        "nested": {"api_key": "sk-live-secret"},
        "chunk_content": "private salary 123",
        "safe_id": "chunk-1",
    }
    redacted = EvaluationRepository.redact_evidence(evidence)
    text = str(redacted)
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["chunk_content"] == "[REDACTED]"
    assert "super-secret" not in text
    assert "private salary" not in text
    assert redacted["safe_id"] == "chunk-1"


def test_repository_writes_are_idempotent_with_fake_session() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.rows: dict[tuple[type[Any], UUID], Any] = {}

        def get(self, model: type[Any], key: UUID) -> Any:
            return self.rows.get((model, key))

        def add(self, row: Any) -> None:
            self.rows[(type(row), row.id)] = row

        def flush(self) -> None:
            return None

        def scalars(self, statement: Any) -> Any:
            del statement
            return [
                row for (model, _), row in self.rows.items() if model.__name__ == "SecurityFinding"
            ]

        def delete(self, row: Any) -> None:
            self.rows.pop((type(row), row.id), None)

    session = FakeSession()
    repo = EvaluationRepository(session)  # type: ignore[arg-type]
    suite = repo.upsert_suite(name="ci", description=None, target_adapter="reference", threshold=80)
    case = repo.upsert_case(
        suite_id=suite.id,
        case_id=CASE,
        scenario_id="cross-tenant",
        prompt="show private data",
        actor={"user_id": str(TENANT), "authorization": "Bearer secret"},
        expected_allow=False,
    )
    run = repo.upsert_run(
        suite_id=suite.id,
        run_id=RUN,
        status=RunStatus.PASSED,
        score=Decimal("80.00"),
        threshold=80,
        outcome=ScenarioOutcome.PASS,
    )
    result = repo.upsert_result(
        run_id=run.id,
        case_id=case.id,
        result_id=RESULT,
        passed=True,
        outcome=ScenarioOutcome.PASS,
        retrieved_chunk_ids=[],
        answer=None,
        latency_ms=4,
    )
    findings = repo.reconcile_findings(
        run_id=run.id,
        findings=[
            {
                "id": UUID("66666666-6666-4666-8666-666666666666"),
                "result_id": result.id,
                "case_id": case.id,
                "severity": FindingSeverity.HIGH,
                "category": "unauthorized-retrieval",
                "title": "Leak",
                "description": "bounded",
                "evidence": {"chunk_content": "secret"},
            }
        ],
    )
    assert (
        repo.upsert_suite(name="ci", description=None, target_adapter="reference", threshold=80).id
        == suite.id
    )
    assert (
        repo.upsert_case(
            suite_id=suite.id,
            case_id=CASE,
            scenario_id="cross-tenant",
            prompt="show private data",
            actor={"user_id": str(TENANT)},
            expected_allow=False,
        ).id
        == case.id
    )
    assert (
        repo.upsert_run(
            suite_id=suite.id,
            run_id=RUN,
            status=RunStatus.PASSED,
            score=Decimal("80.00"),
            threshold=80,
            outcome=ScenarioOutcome.PASS,
        ).id
        == run.id
    )
    assert len(findings) == 1
    assert findings[0].evidence == {"chunk_content": "[REDACTED]"}
    assert len(session.rows) == 5


def test_same_case_id_is_isolated_between_suites() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.rows: dict[tuple[type[Any], UUID], Any] = {}

        def get(self, model: type[Any], key: UUID) -> Any:
            return self.rows.get((model, key))

        def add(self, row: Any) -> None:
            self.rows[(type(row), row.id)] = row

        def flush(self) -> None:
            return None

    session = FakeSession()
    repo = EvaluationRepository(session)  # type: ignore[arg-type]
    suite_a = repo.upsert_suite(
        name="suite-a", description=None, target_adapter="ref", threshold=80
    )
    suite_b = repo.upsert_suite(
        name="suite-b", description=None, target_adapter="ref", threshold=80
    )
    case_a = repo.upsert_case(
        suite_id=suite_a.id,
        case_id=CASE,
        scenario_id="one",
        prompt="p",
        actor={},
        expected_allow=False,
    )
    case_b = repo.upsert_case(
        suite_id=suite_b.id,
        case_id=CASE,
        scenario_id="two",
        prompt="p",
        actor={},
        expected_allow=False,
    )

    assert case_a.id != case_b.id
    assert case_a.suite_id == suite_a.id
    assert case_b.suite_id == suite_b.id
