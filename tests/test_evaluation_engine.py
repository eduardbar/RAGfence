"""In-memory EvaluationEngine contract tests (Work Unit D)."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from ragfence.attacks.runner import ScenarioObservation, ScenarioVerdict
from ragfence.core.enums import Classification, ScenarioOutcome
from ragfence.core.models import AuthorizationContext, EvaluationCase
from ragfence.evaluation import engine


@pytest.fixture
def cases() -> tuple[EvaluationCase, ...]:
    actor = AuthorizationContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )
    return tuple(
        EvaluationCase(
            id=UUID(f"00000000-0000-0000-0000-00000000000{i}"),
            scenario_id=f"scenario-{i}",
            prompt="test",
            actor=actor,
            expected_allow=False,
        )
        for i in range(1, 4)
    )


def test_engine_runs_every_generated_case_and_continues_after_runner_error(
    monkeypatch: pytest.MonkeyPatch, cases: tuple[EvaluationCase, ...]
) -> None:
    monkeypatch.setattr(engine, "generate_cases", lambda seed: cases)
    calls: list[UUID] = []

    def run_case(case: EvaluationCase, target: object) -> ScenarioVerdict:
        calls.append(case.id)
        if case is cases[1]:
            raise RuntimeError("boom")
        observation = ScenarioObservation(case.id, (), "blocked", None, 7)
        return ScenarioVerdict(case, observation, True, "blocked answer")

    monkeypatch.setattr(engine, "run_case", run_case)
    summary = engine.EvaluationEngine(target=object(), seed=19, threshold=80).run()

    assert calls == [case.id for case in cases]
    assert len(summary.results) == 3
    assert summary.results[1].findings[0].category == "target_error"
    assert summary.results[1].passed is False
    assert summary.outcome is ScenarioOutcome.WARNING


def test_engine_derives_metrics_score_and_threshold() -> None:
    summary = engine.EvaluationEngine(target=object(), threshold=0).run()

    assert len(summary.results) == 10
    assert 0 <= summary.score <= 100
    assert summary.passed_threshold is True
    assert "unauthorized_retrieval_rate" in summary.metrics
    assert summary.outcome in set(ScenarioOutcome)


def test_engine_exposes_unavailable_generation_and_cost_metrics_without_values() -> None:
    summary = engine.EvaluationEngine(target=object(), threshold=0).run()

    for name in ("faithfulness", "answer_correctness", "cost_usd"):
        metric = summary.metrics[name]
        assert metric.available is False
        assert metric.value is None
        assert metric.reason


def test_summary_is_canonical_and_byte_deterministic(
    monkeypatch: pytest.MonkeyPatch, cases: tuple[EvaluationCase, ...]
) -> None:
    monkeypatch.setattr(engine, "generate_cases", lambda seed: cases)
    observations = {case.id: ScenarioObservation(case.id, (), "blocked", None, 7) for case in cases}
    monkeypatch.setattr(
        engine,
        "run_case",
        lambda case, target: ScenarioVerdict(case, observations[case.id], True, "ok"),
    )

    first = engine.EvaluationEngine(target=object(), seed=4, threshold=80).run()
    second = engine.EvaluationEngine(target=object(), seed=4, threshold=80).run()

    assert first.canonical_bytes() == second.canonical_bytes()
    assert (
        first.canonical_bytes()
        == json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    )


def test_threshold_equality_passes() -> None:
    summary = engine.EvaluationEngine(target=object(), threshold=80).run()
    assert summary.passed_threshold is (summary.score >= 80)


def test_answer_and_error_are_redacted_in_canonical_summary(
    monkeypatch: pytest.MonkeyPatch, cases: tuple[EvaluationCase, ...]
) -> None:
    monkeypatch.setattr(engine, "generate_cases", lambda seed: cases[:1])
    observation = ScenarioObservation(
        cases[0].id, (), "password=abc Token xyz", "PASSWORD=secret", 1
    )
    monkeypatch.setattr(
        engine,
        "run_case",
        lambda case, target: ScenarioVerdict(case, observation, False, "error password=secret"),
    )

    payload = engine.EvaluationEngine(target=object()).run().to_dict()

    result = payload["results"][0]
    assert "abc" not in json.dumps(payload)
    assert "secret" not in json.dumps(payload)
    assert "abc" not in result["answer"]
    assert "xyz" not in result["answer"]
    assert "secret" not in result["error"]


def test_decimal_threshold_is_retained_in_summary() -> None:
    summary = engine.EvaluationEngine(target=object(), threshold=80.75).run()
    assert summary.threshold == 80.75
