"""Gate decision tests: fail-closed evaluation over control results."""

from __future__ import annotations

import pytest

from ragfence.attacks.generators import EvaluationControl, ExpectedBehavior
from ragfence.evaluation.gate import evaluate_gate
from ragfence.evaluation.matrix_runner import ControlResult, ControlStatus


def _make_control(
    control_id: str = "test-control",
    expected: ExpectedBehavior = ExpectedBehavior.MUST_ALLOW,
    required: bool = True,
) -> EvaluationControl:
    return EvaluationControl(
        id=control_id,
        category="test",
        actor_email="test@example.com",
        actor_tenant="test-tenant",
        target_document="test/doc.md",
        prompt="test prompt",
        expected_behavior=expected,
        identity_required=True,
        retrieval_evidence_required=expected is ExpectedBehavior.MUST_ALLOW,
        required_for_gate=required,
    )


def _make_result(
    control: EvaluationControl,
    status: ControlStatus,
    reason: str = "",
) -> ControlResult:
    from ragfence.evaluation.matrix_runner import ControlObservation

    return ControlResult(
        control=control,
        status=status,
        reason=reason,
        observation=ControlObservation(
            control_id=control.id,
            retrieved_count=1 if status == ControlStatus.PASS else 0,
            answer=None,
            error=None,
            latency_ms=0,
            identity_represented=True,
            evidence_present=True,
        ),
    )


def test_gate_passes_when_all_required_controls_pass() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow, ControlStatus.PASS),
        _make_result(block, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow, block), threshold=80.0)

    assert decision.passed is True
    assert decision.reasons == ()
    assert decision.security_score == 1.0
    assert decision.utility_score == 1.0
    assert decision.overall_score == 1.0


def test_gate_fails_when_required_control_fails() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    results = (_make_result(allow, ControlStatus.FAIL, "required allow returned zero chunks"),)
    decision = evaluate_gate(results, (allow,), threshold=80.0)

    assert decision.passed is False
    assert any("FAIL" in r or "fail" in r.lower() for r in decision.reasons)


def test_gate_fails_when_required_control_inconclusive() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    results = (_make_result(allow, ControlStatus.INCONCLUSIVE, "target error"),)
    decision = evaluate_gate(results, (allow,), threshold=80.0)

    assert decision.passed is False
    assert any("INCONCLUSIVE" in r or "inconclusive" in r.lower() for r in decision.reasons)


def test_gate_fails_when_required_control_skipped() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    results = (_make_result(allow, ControlStatus.SKIPPED),)
    decision = evaluate_gate(results, (allow,), threshold=80.0)

    assert decision.passed is False


def test_gate_fails_when_missing_positive_coverage() -> None:
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (_make_result(block, ControlStatus.PASS),)
    decision = evaluate_gate(results, (block,), threshold=80.0)

    assert decision.passed is False
    assert any("positive" in r.lower() or "must_allow" in r.lower() for r in decision.reasons)


def test_gate_fails_when_missing_negative_coverage() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    results = (_make_result(allow, ControlStatus.PASS),)
    decision = evaluate_gate(results, (allow,), threshold=80.0)

    assert decision.passed is False
    assert any("negative" in r.lower() or "must_block" in r.lower() for r in decision.reasons)


def test_gate_fails_when_score_below_threshold() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow, ControlStatus.PASS),
        _make_result(block, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow, block), threshold=101.0)

    assert decision.passed is False
    assert any("threshold" in r.lower() for r in decision.reasons)


def test_gate_fails_on_empty_results() -> None:
    decision = evaluate_gate((), (), threshold=80.0)

    assert decision.passed is False


def test_score_formula_security_and_utility_separate() -> None:
    allow1 = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    allow2 = _make_control("allow-2", ExpectedBehavior.MUST_ALLOW)
    block1 = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow1, ControlStatus.PASS),
        _make_result(allow2, ControlStatus.FAIL, "zero chunks"),
        _make_result(block1, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow1, allow2, block1), threshold=0.0)

    assert decision.security_score == 1.0
    assert decision.utility_score == 0.5
    assert decision.overall_score == 0.75


def test_canonical_threshold_80_requires_overall_gte_80_percent() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow, ControlStatus.PASS),
        _make_result(block, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow, block), threshold=80.0)
    assert decision.passed is True


def test_canonical_threshold_0_8_means_0_8_percent_not_80() -> None:
    allow = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow, ControlStatus.PASS),
        _make_result(block, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow, block), threshold=0.8)
    assert decision.overall_score == 1.0
    assert decision.passed is True
    assert not any("threshold" in r.lower() for r in decision.reasons)


def test_overall_score_rounded_to_two_decimals() -> None:
    allow1 = _make_control("allow-1", ExpectedBehavior.MUST_ALLOW)
    allow2 = _make_control("allow-2", ExpectedBehavior.MUST_ALLOW)
    allow3 = _make_control("allow-3", ExpectedBehavior.MUST_ALLOW)
    block = _make_control("block-1", ExpectedBehavior.MUST_BLOCK)
    results = (
        _make_result(allow1, ControlStatus.PASS),
        _make_result(allow2, ControlStatus.PASS),
        _make_result(allow3, ControlStatus.FAIL, "zero chunks"),
        _make_result(block, ControlStatus.PASS),
    )
    decision = evaluate_gate(results, (allow1, allow2, allow3, block), threshold=0.0)

    assert decision.utility_score == pytest.approx(2 / 3)
    assert decision.overall_score == round((1.0 + 2 / 3) / 2, 2)
