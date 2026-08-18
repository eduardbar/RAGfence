"""Work Unit E tests for provider-aware generation evaluation gating."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from ragfence.attacks.runner import ScenarioObservation, ScenarioVerdict
from ragfence.core.enums import Classification, ScenarioOutcome
from ragfence.core.models import AuthorizationContext, EvaluationCase
from ragfence.evaluation import engine


@dataclass(frozen=True)
class Chunk:
    chunk_id: UUID


def _case(scenario_id: str, *, expected_allow: bool = True) -> EvaluationCase:
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
    return EvaluationCase(
        id=uuid4(),
        scenario_id=scenario_id,
        prompt="question",
        actor=actor,
        expected_allow=expected_allow,
    )


def _run_with(
    monkeypatch: pytest.MonkeyPatch,
    cases: tuple[EvaluationCase, ...],
    verdicts: dict[UUID, ScenarioVerdict],
    **kwargs: object,
):
    monkeypatch.setattr(engine, "generate_cases", lambda seed: cases)
    monkeypatch.setattr(engine, "run_case", lambda case, target: verdicts[case.id])
    return engine.EvaluationEngine(target=object(), **kwargs).run()


def test_fake_provider_skips_generation_but_keeps_security_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation = _case("prompt-injection")
    retrieval = _case("acl-bypass", expected_allow=False)
    verdicts = {
        generation.id: ScenarioVerdict(
            generation,
            ScenarioObservation(generation.id, (), "safe answer", None, 5),
            True,
            "ok",
        ),
        retrieval.id: ScenarioVerdict(
            retrieval,
            ScenarioObservation(retrieval.id, (Chunk(uuid4()),), None, None, 3),
            False,
            "unexpected retrieval",
        ),
    }

    summary = _run_with(
        monkeypatch,
        (generation, retrieval),
        verdicts,
        provider_metadata={"provider": "fake", "real": False},
    )

    assert summary.results[0].outcome is ScenarioOutcome.WARNING
    assert "skipped: no_real_provider" in summary.results[0].reason
    assert any(f.category == "generation_skipped" for f in summary.results[0].findings)
    assert summary.metrics["faithfulness"].available is False
    assert summary.metrics["answer_correctness"].available is False
    assert summary.metrics["unauthorized_retrieval_rate"].available is True
    assert summary.metrics["leakage_rate"].available is True


def test_real_provider_enables_generation_and_operational_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case("prompt-injection")
    verdict = ScenarioVerdict(
        case, ScenarioObservation(case.id, (), "blocked", None, 12), True, "blocked answer"
    )

    summary = _run_with(
        monkeypatch,
        (case,),
        {case.id: verdict},
        provider_metadata={
            "provider": "ollama",
            "real": True,
            "prompt_tokens": 7,
            "completion_tokens": 2,
        },
    )

    assert summary.metrics["faithfulness"].available is True
    assert summary.metrics["answer_correctness"].available is True
    assert summary.metrics["latency_ms"].available is True
    assert summary.metrics["prompt_tokens"].value == 7
    assert summary.metrics["completion_tokens"].value == 2


def test_real_provider_failure_fails_without_fake_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _case("prompt-injection")
    verdict = ScenarioVerdict(
        case,
        ScenarioObservation(case.id, (), None, "provider request timed out", 12),
        False,
        "target error: provider request timed out",
    )

    summary = _run_with(
        monkeypatch,
        (case,),
        {case.id: verdict},
        provider_metadata={"provider": "openai", "real": True},
    )

    result = summary.results[0]
    assert result.passed is False
    assert result.answer is None
    assert result.error == "provider request timed out"
    assert summary.metrics["faithfulness"].available is False
    assert summary.metrics["answer_correctness"].available is False
    assert not any("fake" in str(f.evidence).casefold() for f in result.findings)


@pytest.mark.parametrize(
    "provider_error",
    ["provider response was malformed", "provider rate limit exhausted"],
)
def test_real_provider_malformed_or_rate_limit_failure_is_not_replaced(
    monkeypatch: pytest.MonkeyPatch, provider_error: str
) -> None:
    case = _case("prompt-injection")
    verdict = ScenarioVerdict(
        case,
        ScenarioObservation(case.id, (), None, provider_error, 9),
        False,
        f"target error: {provider_error}",
    )

    summary = _run_with(
        monkeypatch,
        (case,),
        {case.id: verdict},
        provider_metadata={"provider": "anthropic", "real": True},
    )

    result = summary.results[0]
    assert result.passed is False
    assert result.answer is None
    assert result.error == provider_error
    assert "fake" not in str(result.to_dict()).casefold()
