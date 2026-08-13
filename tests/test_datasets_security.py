"""Fixture security semantics through the policy engine (PR 1, tasks 1.3, 1.7).

Spec reference: openspec/changes/ragfence-acme-dataset/specs/synthetic-dataset/spec.md
- Synthetic Document Corpus / Scenario: Per-department coverage
- Synthetic Document Corpus / Scenario: Key security fixtures exist
- Fixture Security Semantics / Scenarios: Engineering user denied on CFO.pdf,
  Same-department allow, Executives group allowlist grants access,
  Confidential clearance denied on board-plan.pdf
- In-Memory Consumption Path / Scenario: Strict typing enforced
"""

import uuid

import pytest
from pydantic import ValidationError

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.core.models import DocumentACL
from ragfence.datasets import SEED, build_acme_corp
from ragfence.datasets.constants import CFO_SALARY_LITERAL
from ragfence.policies.decision import decide

CFO_PATH = "finance/payroll/cfo-payroll-summary.pdf"
BOARD_PATH = "executive/strategy/2026-board-plan.pdf"
ENGINEERING_EMPLOYEE = "engineering_employee@acme-corp.example"
FINANCE_ANALYST = "finance_analyst@acme-corp.example"
CEO = "ceo@acme-corp.example"
FINANCE_LEAD = "finance_lead@acme-corp.example"


def test_every_department_has_a_ready_document_with_acl() -> None:
    ds = build_acme_corp(SEED)
    for slug in ds.departments:
        dept_docs = [doc for path, doc in ds.documents.items() if path.startswith(f"{slug}/")]
        assert dept_docs
        for doc in dept_docs:
            assert doc.status == DocumentStatus.READY
            assert doc.title
            assert doc.source
            assert doc.checksum
            assert doc.acl is not None


def test_cfo_policy_is_confidential_and_finance_scoped() -> None:
    ds = build_acme_corp(SEED)
    cfo = ds.documents[CFO_PATH]
    assert cfo.acl.classification == Classification.CONFIDENTIAL
    assert cfo.acl.department_id == ds.departments["finance"].id
    assert CFO_SALARY_LITERAL in cfo.body


def test_board_plan_policy_has_no_department_scope() -> None:
    ds = build_acme_corp(SEED)
    board = ds.documents[BOARD_PATH]
    assert board.acl.classification == Classification.RESTRICTED
    assert board.policy.department_id is None
    assert board.acl.department_id is None
    assert board.policy.allowed_group_ids == {ds.groups["executives"].id}


def test_engineering_user_denied_on_cfo_pdf() -> None:
    """S10: engineering/internal denied; engine reports the first failing rule."""
    ds = build_acme_corp(SEED)
    policy = ds.documents[CFO_PATH].policy
    ctx = ds.context_for(ENGINEERING_EMPLOYEE)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons
    assert decision.reasons == ["classification_escalation"]


def test_finance_analyst_allowed_on_cfo_pdf() -> None:
    """S11: same-department allow (finance, confidential)."""
    ds = build_acme_corp(SEED)
    policy = ds.documents[CFO_PATH].policy
    ctx = ds.context_for(FINANCE_ANALYST)
    assert decide(policy, ctx).allowed is True


def test_executives_group_allowlist_grants_board_plan() -> None:
    """S12: restricted-clearance user in the executives group is allowed."""
    ds = build_acme_corp(SEED)
    policy = ds.documents[BOARD_PATH].policy
    ctx = ds.context_for(CEO)
    assert decide(policy, ctx).allowed is True


def test_confidential_finance_user_denied_on_board_plan() -> None:
    """S13: confidential-clearance finance user not in executives is denied."""
    ds = build_acme_corp(SEED)
    policy = ds.documents[BOARD_PATH].policy
    ctx = ds.context_for(FINANCE_LEAD)
    decision = decide(policy, ctx)
    assert decision.allowed is False
    assert decision.reasons == ["classification_escalation"]


def test_unknown_classification_raises_validation_error() -> None:
    """S7: an unknown classification value is rejected on construction."""
    with pytest.raises(ValidationError):
        DocumentACL(
            document_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            department_id=None,
            classification="top_secret",
            allowed_user_ids=set(),
            allowed_group_ids=set(),
        )


def test_acl_extra_field_raises_validation_error() -> None:
    """S7: an ACL with extra fields is rejected on construction."""
    with pytest.raises(ValidationError):
        DocumentACL(
            document_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            department_id=None,
            classification=Classification.CONFIDENTIAL,
            allowed_user_ids=set(),
            allowed_group_ids=set(),
            extra_field="spoofed",
        )
