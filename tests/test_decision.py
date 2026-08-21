"""Policy decision tests (task 3.1).

Spec reference: openspec/changes/ragfence-foundation/specs/policy-engine/spec.md
- Decision Function / Scenario: Cross-department denial (success criterion)
- Deny-by-Default / Scenario: No implicit access
- Classification Escalation / Scenario: Clearance below document
- Explicit Grants Override Department / Scenario: Allowlisted user crosses departments
- Department Scoping / Scenario: Same-department allow
"""

import uuid
from datetime import datetime
from uuid import UUID

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, DocumentPolicy
from ragfence.policies.decision import decide

ENGINEERING = uuid.uuid4()
FINANCE = uuid.uuid4()


def _policy(
    *, classification: Classification = Classification.INTERNAL, department_id: UUID | None = None
) -> DocumentPolicy:
    return DocumentPolicy(
        classification=classification,
        department_id=department_id,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
    )


def _ctx(
    *,
    department_id: UUID | None,
    classification: Classification = Classification.INTERNAL,
    user_id: UUID | None = None,
    groups: set[UUID] | None = None,
) -> AuthorizationContext:
    user = user_id or uuid.uuid4()
    return AuthorizationContext(
        tenant_id=uuid.uuid4(),
        user_id=user,
        department_id=department_id,
        classification=classification,
        allowed_user_ids={user},
        allowed_group_ids=groups or set(),
        is_authenticated=True,
        source="synthetic",
    )


def test_cross_department_denial_cfo_success_criterion() -> None:
    """GIVEN finance/confidential policy and engineering/internal ctx, THEN denied with reasons."""
    policy = _policy(classification=Classification.CONFIDENTIAL, department_id=FINANCE)
    ctx = _ctx(department_id=ENGINEERING, classification=Classification.INTERNAL)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons
    assert any("classification" in reason for reason in decision.reasons)


def test_no_implicit_access_when_department_null() -> None:
    policy = _policy(department_id=None)
    ctx = _ctx(department_id=ENGINEERING)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons == ["no_implicit_department_access"]


def test_clearance_below_document_denied() -> None:
    policy = _policy(classification=Classification.RESTRICTED, department_id=None)
    ctx = _ctx(department_id=ENGINEERING, classification=Classification.INTERNAL)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons == ["classification_escalation"]


def test_unauthenticated_context_is_denied_before_any_grant() -> None:
    """An unauthenticated context is never authorized, including by an explicit ACL grant."""
    user = uuid.uuid4()
    policy = DocumentPolicy(
        classification=Classification.INTERNAL,
        department_id=FINANCE,
        allowed_user_ids={user},
        allowed_group_ids=set(),
    )
    ctx = _ctx(department_id=FINANCE, user_id=user).model_copy(update={"is_authenticated": False})

    decision = decide(policy, ctx)

    assert decision.allowed is False
    assert decision.reasons == ["unauthenticated"]


def test_allowlisted_user_crosses_departments() -> None:
    user = uuid.uuid4()
    policy = DocumentPolicy(
        classification=Classification.INTERNAL,
        department_id=FINANCE,
        allowed_user_ids={user},
        allowed_group_ids=set(),
    )
    ctx = _ctx(department_id=ENGINEERING, user_id=user)
    decision = decide(policy, ctx)
    assert decision.allowed is True
    assert decision.reasons == []


def test_allowlisted_group_crosses_departments() -> None:
    group = uuid.uuid4()
    policy = DocumentPolicy(
        classification=Classification.INTERNAL,
        department_id=FINANCE,
        allowed_user_ids=set(),
        allowed_group_ids={group},
    )
    ctx = _ctx(department_id=ENGINEERING, groups={group})
    decision = decide(policy, ctx)
    assert decision.allowed is True
    assert decision.reasons == []


def test_same_department_allow() -> None:
    dept = uuid.uuid4()
    policy = _policy(department_id=dept)
    ctx = _ctx(department_id=dept)
    decision = decide(policy, ctx)
    assert decision.allowed is True
    assert decision.reasons == []


def test_deny_by_default_when_department_mismatch_without_grant() -> None:
    policy = _policy(department_id=FINANCE)
    ctx = _ctx(department_id=ENGINEERING)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons == ["deny_by_default"]


def test_decision_records_evaluated_at() -> None:
    decision = decide(_policy(department_id=None), _ctx(department_id=ENGINEERING))
    assert isinstance(decision.evaluated_at, datetime)
