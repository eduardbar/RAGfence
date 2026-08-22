"""Indirect prompt-injection cases carried by retrieved document content."""

import json

from ragfence.attacks.generators import generate_injection_cases
from ragfence.attacks.runner import run_case
from ragfence.evaluation.report import build_report, render_json


class SafeTarget:
    def retrieve(self, request):
        return []

    def answer(self, request, chunks):
        return "blocked"


def test_injection_cases_are_deterministic_and_non_gate() -> None:
    first = [case.model_dump_json() for case in generate_injection_cases(seed=42)]
    second = [case.model_dump_json() for case in generate_injection_cases(seed=42)]

    assert first == second
    cases = generate_injection_cases(seed=42)
    assert len(cases) == 3
    assert {case.required_for_gate for case in cases} == {False}
    assert {case.scenario_id for case in cases} == {
        "indirect-prompt-injection-exfiltrate-tenant",
        "indirect-prompt-injection-override-acl",
        "indirect-prompt-injection-reveal-hidden-chunks",
    }
    assert all(case.retrieved_document_content for case in cases)


def test_injection_content_is_not_emitted_in_rendered_findings() -> None:
    case = generate_injection_cases(seed=42)[0]
    verdict = run_case(case, SafeTarget())
    assert verdict.passed is True

    # The attack payload is intentionally secret-shaped, but findings contain
    # only bounded, redaction-safe evidence when rendered.
    from ragfence.evaluation.engine import EvaluationEngine

    result = EvaluationEngine(SafeTarget())._result(verdict)
    rendered = render_json(build_report(None, [result]))
    assert "TENANT_SECRET=" not in rendered
    assert "do-not-render" not in rendered


def test_runner_executes_all_injection_cases_without_gate_effect() -> None:
    cases = generate_injection_cases(seed=7)
    verdicts = [run_case(case, SafeTarget()) for case in cases]

    assert all(verdict.passed for verdict in verdicts)
    assert all(verdict.observation.error is None for verdict in verdicts)
    # Non-gate cases are intentionally not part of the legacy generated suite.
    from ragfence.attacks.generators import generate_cases

    assert all(case.required_for_gate is False for case in cases)
    assert not {case.id for case in cases} & {case.id for case in generate_cases(seed=7)}
