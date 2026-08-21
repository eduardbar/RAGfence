"""Domain model tests (tasks 2.2, 2.3).

Spec reference: openspec/changes/ragfence-foundation/specs/domain-models/spec.md
- Pydantic Models / Scenario: Validation on construction
- JSONB Serialization / Scenario: Round-trip through JSON
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import pytest
from pydantic import ValidationError

from ragfence.core.enums import Classification, FindingSeverity
from ragfence.core.models import (
    AttackScenario,
    AuthorizationContext,
    Citation,
    DocumentACL,
    DocumentPolicy,
    EvaluationCase,
    EvaluationResult,
    PolicyDecision,
    RetrievalRequest,
    RetrievedChunk,
    SecurityFinding,
)

Source = Literal["synthetic", "oidc", "api_token"]


def _uuid() -> UUID:
    return uuid.uuid4()


def _ctx(*, source: Source = "synthetic") -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=_uuid(),
        user_id=_uuid(),
        department_id=_uuid(),
        classification=Classification.INTERNAL,
        allowed_user_ids={_uuid()},
        allowed_group_ids={_uuid()},
        is_authenticated=True,
        source=source,
    )


def _ctx_with(**overrides: object) -> AuthorizationContext:
    fields: dict[str, object] = {
        "tenant_id": _uuid(),
        "user_id": _uuid(),
        "department_id": None,
        "classification": Classification.INTERNAL,
        "allowed_user_ids": set(),
        "allowed_group_ids": set(),
        "is_authenticated": True,
        "source": "synthetic",
    }
    fields.update(overrides)
    return AuthorizationContext(**fields)


def test_authorization_context_construction() -> None:
    ctx = _ctx()
    assert ctx.is_authenticated is True
    assert ctx.classification is Classification.INTERNAL
    assert isinstance(ctx.allowed_user_ids, set)
    assert isinstance(ctx.allowed_group_ids, set)
    assert ctx.source == "synthetic"


def test_document_acl_construction() -> None:
    acl = DocumentACL(
        document_id=_uuid(),
        tenant_id=_uuid(),
        department_id=None,
        classification=Classification.CONFIDENTIAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
    )
    assert acl.department_id is None
    assert acl.classification is Classification.CONFIDENTIAL
    assert acl.allowed_user_ids == set()


def test_document_policy_construction() -> None:
    policy = DocumentPolicy(
        classification=Classification.RESTRICTED,
        department_id=None,
        allowed_user_ids={_uuid()},
        allowed_group_ids={_uuid()},
    )
    assert policy.classification is Classification.RESTRICTED
    assert policy.department_id is None


def test_policy_decision_construction() -> None:
    decision = PolicyDecision(
        allowed=False, reasons=["classification_escalation"], evaluated_at=datetime.now(UTC)
    )
    assert decision.allowed is False
    assert decision.reasons == ["classification_escalation"]


def test_retrieval_request_construction() -> None:
    request = RetrievalRequest(query="quarterly report", authorization=_ctx())
    assert request.query == "quarterly report"
    assert request.top_k == 10
    assert request.filters == {}


@pytest.mark.parametrize("top_k", [0, -1, 51, 10_000])
def test_retrieval_request_rejects_unbounded_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(query="quarterly report", authorization=_ctx(), top_k=top_k)


def test_retrieved_chunk_construction() -> None:
    chunk = RetrievedChunk(
        chunk_id=_uuid(),
        document_id=_uuid(),
        document_title="CFO Memo",
        chunk_index=3,
        content="text",
        score=0.95,
        metadata={"source": "sharepoint"},
    )
    assert chunk.chunk_index == 3
    assert chunk.score == 0.95
    assert chunk.metadata["source"] == "sharepoint"


def test_citation_construction() -> None:
    citation = Citation(
        document_id=_uuid(), document_title="CFO Memo", chunk_index=2, snippet="snippet"
    )
    assert citation.document_title == "CFO Memo"
    assert citation.snippet == "snippet"


def test_attack_scenario_construction() -> None:
    scenario = AttackScenario(
        id="cross-tenant-retrieval",
        name="Cross-tenant retrieval",
        description="d",
        target_stage="retrieval",
        expected_behavior="must_block",
    )
    assert scenario.target_stage == "retrieval"
    assert scenario.expected_behavior == "must_block"


def test_evaluation_case_construction() -> None:
    case = EvaluationCase(
        id=_uuid(),
        scenario_id="cross-tenant-retrieval",
        prompt="p",
        actor=_ctx(),
        expected_allow=False,
    )
    assert case.expected_allow is False
    assert case.actor.classification is Classification.INTERNAL


def test_security_finding_construction() -> None:
    finding = SecurityFinding(
        id=_uuid(),
        severity=FindingSeverity.HIGH,
        category="unauthorized-retrieval",
        title="leak",
        description="d",
        evidence={"prompt": "p"},
    )
    assert finding.severity is FindingSeverity.HIGH
    assert finding.evidence["prompt"] == "p"


def test_evaluation_result_construction() -> None:
    result = EvaluationResult(
        id=_uuid(),
        case_id=_uuid(),
        passed=True,
        findings=[],
        retrieved=[],
        answer="ok",
        latency_ms=12,
    )
    assert result.passed is True
    assert result.answer == "ok"
    assert result.latency_ms == 12


def test_invalid_classification_rejected() -> None:
    with pytest.raises(ValidationError):
        _ctx_with(classification="top_secret")


def test_invalid_source_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        _ctx_with(source="hacker")


def test_invalid_user_id_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _ctx_with(user_id="not-a-uuid")


def test_invalid_allowlist_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _ctx_with(allowed_user_ids="nope")


def test_document_policy_requires_classification() -> None:
    with pytest.raises(ValidationError):
        DocumentPolicy()


def test_authorization_context_jsonb_roundtrip_is_lossless() -> None:
    original = _ctx(source="synthetic")
    dumped = original.model_dump_json()
    parsed = json.loads(dumped)
    assert isinstance(parsed["allowed_user_ids"], list)
    assert isinstance(parsed["allowed_group_ids"], list)
    assert isinstance(parsed["department_id"], str)
    roundtripped = AuthorizationContext.model_validate_json(dumped)
    assert roundtripped == original
    assert roundtripped.allowed_user_ids == original.allowed_user_ids
    assert roundtripped.allowed_group_ids == original.allowed_group_ids
    assert roundtripped.department_id == original.department_id
    assert all(isinstance(member, UUID) for member in roundtripped.allowed_user_ids)


def test_authorization_context_jsonb_roundtrip_preserves_source() -> None:
    for source in ("synthetic", "oidc", "api_token"):
        original = _ctx(source=source)
        roundtripped = AuthorizationContext.model_validate_json(original.model_dump_json())
        assert roundtripped.source == source


def test_authorization_context_jsonb_roundtrip_null_department() -> None:
    original = AuthorizationContext(
        tenant_id=_uuid(),
        user_id=_uuid(),
        department_id=None,
        classification=Classification.PUBLIC,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=False,
        source="api_token",
    )
    roundtripped = AuthorizationContext.model_validate_json(original.model_dump_json())
    assert roundtripped == original
    assert roundtripped.department_id is None
    assert roundtripped.classification is Classification.PUBLIC
