"""Matrix runner tests: declarative control execution against fake targets."""

from __future__ import annotations

from uuid import UUID

from ragfence.attacks.generators import ExpectedBehavior, default_evaluation_controls
from ragfence.core.models import RetrievalRequest, RetrievedChunk
from ragfence.evaluation.gate import evaluate_gate
from ragfence.evaluation.matrix_runner import ControlStatus, run_matrix


class _BlockAllTarget:
    """Target that returns zero chunks for every request."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        del request
        return []


class _AllowAllTarget:
    """Target that returns one chunk for every request from the target document."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        document_id = request.filters.get("document_id", "00000000-0000-0000-0000-000000000002")
        return [
            RetrievedChunk(
                chunk_id="00000000-0000-0000-0000-000000000001",
                document_id=document_id,
                document_title="test",
                chunk_index=0,
                content="test content",
                score=1.0,
                metadata={},
            )
        ]


class _RaisingTarget:
    """Target that raises an exception for every request."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        del request
        raise RuntimeError("target error: connection failed")


def test_block_all_target_fails_must_allow_and_passes_must_block() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_BlockAllTarget(), controls)

    assert len(results) == len(controls)
    for control, result in zip(controls, results, strict=True):
        assert result.control is control
        if control.expected_behavior == ExpectedBehavior.MUST_ALLOW:
            assert result.status == ControlStatus.FAIL
            assert "zero chunks" in result.reason
        else:
            assert result.status == ControlStatus.PASS


def test_allow_all_target_fails_must_block_and_passes_must_allow() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_AllowAllTarget(), controls)

    assert len(results) == len(controls)
    for control, result in zip(controls, results, strict=True):
        assert result.control is control
        if control.expected_behavior == ExpectedBehavior.MUST_BLOCK:
            assert result.status == ControlStatus.FAIL
            assert "unauthorized retrieval" in result.reason
        else:
            assert result.status == ControlStatus.PASS


def test_raising_target_produces_inconclusive_for_all_controls() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_RaisingTarget(), controls)

    assert len(results) == len(controls)
    for result in results:
        assert result.status == ControlStatus.INCONCLUSIVE
        assert "target error" in result.reason


def test_identity_not_represented_produces_inconclusive() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_AllowAllTarget(), controls, identity_represented=False)

    assert len(results) == len(controls)
    for control, result in zip(controls, results, strict=True):
        assert control.identity_required is True
        assert result.status == ControlStatus.INCONCLUSIVE
        assert "identity not represented" in result.reason


def test_skip_non_required_skips_only_non_required_controls() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_BlockAllTarget(), controls, skip_non_required=True)

    assert len(results) == len(controls)
    for control, result in zip(controls, results, strict=True):
        if control.required_for_gate:
            assert result.status != ControlStatus.SKIPPED
        else:
            assert result.status == ControlStatus.SKIPPED


def test_order_preserved_and_latency_non_negative() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_AllowAllTarget(), controls)

    assert [result.control.id for result in results] == [control.id for control in controls]
    for result in results:
        assert result.observation.latency_ms >= 0


class _UnrelatedDocumentTarget:
    """Target that returns chunks from a fixed unrelated document (spec R1.2)."""

    UNRELATED_ID = UUID("99999999-9999-9999-9999-999999999999")

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        del request
        return [
            RetrievedChunk(
                chunk_id="00000000-0000-0000-0000-000000000001",
                document_id=self.UNRELATED_ID,
                document_title="unrelated",
                chunk_index=0,
                content="unrelated content",
                score=1.0,
                metadata={},
            )
        ]


def test_must_allow_fails_when_chunks_from_unrelated_document() -> None:
    controls = default_evaluation_controls()
    results = run_matrix(_UnrelatedDocumentTarget(), controls)

    for control, result in zip(controls, results, strict=True):
        if control.expected_behavior == ExpectedBehavior.MUST_ALLOW:
            assert result.status == ControlStatus.FAIL
            assert "no chunk from target document" in result.reason
        else:
            assert result.status == ControlStatus.FAIL
            assert "unauthorized retrieval" in result.reason


def test_unrelated_chunks_gate_fails_even_when_blocks_pass() -> None:
    class _BlocksOnlyTarget:
        def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
            return []

    class _MixedTarget:
        def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
            if request.filters.get("document_id"):
                return [
                    RetrievedChunk(
                        chunk_id="00000000-0000-0000-0000-000000000001",
                        document_id=UUID("99999999-9999-9999-9999-999999999999"),
                        document_title="unrelated",
                        chunk_index=0,
                        content="unrelated",
                        score=1.0,
                        metadata={},
                    )
                ]
            return []

    controls = default_evaluation_controls()
    results = run_matrix(_MixedTarget(), controls)
    gate = evaluate_gate(results, controls, threshold=80.0)
    assert gate.passed is False
    assert any("no chunk from target document" in r for r in gate.reasons)


def test_cleanup_failure_marks_control_inconclusive() -> None:
    class _FailingCleanupTarget:
        def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
            return []

        def materialize_precondition(self, control: object) -> object:
            def cleanup() -> None:
                raise RuntimeError("cleanup failed")

            return cleanup

    controls = default_evaluation_controls()
    soft_delete_controls = [c for c in controls if c.category == "soft-deletion"]
    assert soft_delete_controls, "expected at least one soft-deletion control"

    results = run_matrix(_FailingCleanupTarget(), controls)
    for control, result in zip(controls, results, strict=True):
        if control.category == "soft-deletion":
            assert result.status == ControlStatus.INCONCLUSIVE
            assert "postcondition restoration failed" in result.reason
