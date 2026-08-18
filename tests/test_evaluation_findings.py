from uuid import UUID, uuid4

from ragfence.attacks.runner import ScenarioObservation, ScenarioVerdict
from ragfence.core.enums import FindingSeverity, ScenarioOutcome
from ragfence.core.models import EvaluationCase
from ragfence.evaluation.findings import derive_findings, outcome_for_findings


def _case(*, expected_allow: bool = True) -> EvaluationCase:
    from ragfence.core.enums import Classification
    from ragfence.core.models import AuthorizationContext

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
        scenario_id="case",
        prompt="q",
        actor=actor,
        expected_allow=expected_allow,
    )


def _verdict(*, expected_allow: bool = True, chunks=(), answer=None, error=None):
    case = _case(expected_allow=expected_allow)
    observation = ScenarioObservation(case.id, tuple(chunks), answer, error, 4)
    return ScenarioVerdict(case, observation, error is None and not chunks, "reason")


def test_clean_case_has_no_findings_and_passes():
    findings = derive_findings(_verdict())
    assert findings == []
    assert outcome_for_findings(findings) is ScenarioOutcome.PASS


def test_unauthorized_retrieval_is_high_and_identifies_chunks_without_content():
    class Chunk:
        chunk_id = UUID("11111111-1111-1111-1111-111111111111")
        document_id = UUID("22222222-2222-2222-2222-222222222222")
        content = "private payroll content"

    findings = derive_findings(_verdict(expected_allow=False, chunks=(Chunk(),)))
    assert len(findings) == 1
    assert findings[0].severity is FindingSeverity.HIGH
    assert findings[0].category == "unauthorized_retrieval"
    assert str(Chunk.chunk_id) in str(findings[0].evidence)
    assert "private payroll content" not in str(findings[0].evidence)
    assert outcome_for_findings(findings) is ScenarioOutcome.FAIL


def test_target_error_is_bounded_medium_finding():
    findings = derive_findings(_verdict(error="x" * 1000))
    assert findings[0].severity is FindingSeverity.MEDIUM
    assert findings[0].category == "target_error"
    assert len(findings[0].evidence["error"]) <= 512
    assert outcome_for_findings(findings) is ScenarioOutcome.WARNING


def test_answer_marker_is_critical_and_redacted():
    findings = derive_findings(
        _verdict(expected_allow=False, answer="The secret payroll password is 123")
    )
    assert findings[0].severity is FindingSeverity.CRITICAL
    assert findings[0].category == "answer_leakage"
    assert "secret" not in str(findings[0].evidence).casefold()
    assert outcome_for_findings(findings) is ScenarioOutcome.CRITICAL


def test_outcome_mapping_uses_highest_severity():
    assert outcome_for_findings([FindingSeverity.LOW]) is ScenarioOutcome.WARNING
    assert outcome_for_findings([FindingSeverity.MEDIUM]) is ScenarioOutcome.WARNING
    assert outcome_for_findings([FindingSeverity.HIGH]) is ScenarioOutcome.FAIL
    assert outcome_for_findings([FindingSeverity.CRITICAL]) is ScenarioOutcome.CRITICAL
    assert (
        outcome_for_findings([FindingSeverity.LOW, FindingSeverity.CRITICAL])
        is ScenarioOutcome.CRITICAL
    )
