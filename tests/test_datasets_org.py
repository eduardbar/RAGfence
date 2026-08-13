"""Org model shape and identifier stability tests (PR 1, task 1.1).

Spec reference: openspec/changes/ragfence-acme-dataset/specs/synthetic-dataset/spec.md
- Deterministic Org Model / Scenario: Fixture shape is complete
- Deterministic Org Model / Scenario: Identifiers are stable
"""

from uuid import UUID

from ragfence.core.enums import Classification
from ragfence.datasets import SEED, build_acme_corp

EXPECTED_DEPARTMENTS = {"engineering", "hr", "finance", "legal", "executive"}
ALL_TIERS = {
    Classification.PUBLIC,
    Classification.INTERNAL,
    Classification.CONFIDENTIAL,
    Classification.RESTRICTED,
}
EXPECTED_DOCUMENTS = {
    "engineering/architecture-overview.md",
    "hr/employee-handbook.md",
    "finance/payroll/cfo-payroll-summary.pdf",
    "legal/vendor-msa.pdf",
    "executive/strategy/2026-board-plan.pdf",
}


def test_one_tenant_and_five_departments() -> None:
    ds = build_acme_corp(SEED)
    assert ds.tenant.slug == "acme-corp"
    assert ds.tenant.name == "Acme Corp"
    assert len(ds.departments) == 5
    assert set(ds.departments) == EXPECTED_DEPARTMENTS


def test_users_cover_all_four_classification_tiers() -> None:
    ds = build_acme_corp(SEED)
    assert len(ds.users) == 7
    assert {user.classification for user in ds.users.values()} == ALL_TIERS


def test_users_assigned_to_design_departments() -> None:
    ds = build_acme_corp(SEED)
    expected = {
        "engineering_employee@acme-corp.example": "engineering",
        "hr_coordinator@acme-corp.example": "hr",
        "finance_analyst@acme-corp.example": "finance",
        "legal_counsel@acme-corp.example": "legal",
        "ceo@acme-corp.example": "executive",
        "cfo@acme-corp.example": "executive",
        "finance_lead@acme-corp.example": "finance",
    }
    assert set(ds.users) == set(expected)
    for email, slug in expected.items():
        assert ds.users[email].department_id == ds.departments[slug].id


def test_user_groups_map_existing_users_and_groups() -> None:
    ds = build_acme_corp(SEED)
    user_ids = {user.id for user in ds.users.values()}
    group_ids = {group.id for group in ds.groups.values()}
    assert ds.user_groups
    for user_id, group_id in ds.user_groups:
        assert user_id in user_ids
        assert group_id in group_ids
    executives = ds.groups["executives"].id
    finance_leads = ds.groups["finance-leads"].id
    ceo_id = ds.users["ceo@acme-corp.example"].id
    cfo_id = ds.users["cfo@acme-corp.example"].id
    assert {user_id for user_id, group_id in ds.user_groups if group_id == executives} == {
        ceo_id,
        cfo_id,
    }
    assert {user_id for user_id, group_id in ds.user_groups if group_id == finance_leads} == {
        ds.users["finance_lead@acme-corp.example"].id
    }


def test_document_set_matches_corpus_shape() -> None:
    ds = build_acme_corp(SEED)
    assert set(ds.documents) == EXPECTED_DOCUMENTS


def test_identifiers_are_stable_across_runs() -> None:
    first = build_acme_corp(SEED)
    second = build_acme_corp(SEED)
    assert first.tenant.id == second.tenant.id
    assert {d.id for d in first.departments.values()} == {d.id for d in second.departments.values()}
    assert {g.id for g in first.groups.values()} == {g.id for g in second.groups.values()}
    assert {u.id for u in first.users.values()} == {u.id for u in second.users.values()}
    assert {d.id for d in first.documents.values()} == {d.id for d in second.documents.values()}
    assert first.user_groups == second.user_groups


def test_key_identifiers_are_fixed_uuid5_values() -> None:
    """S1: identifiers are fixed stable UUIDs — pin the frozen values."""
    ds = build_acme_corp(SEED)
    assert ds.tenant.id == UUID("d407148a-8d1c-5f85-ba86-e705caf7ec48")
    assert ds.users["ceo@acme-corp.example"].id == UUID("7139f2cc-029f-5863-8ba4-037858ca2300")
    assert ds.documents["finance/payroll/cfo-payroll-summary.pdf"].id == UUID(
        "281f4c51-2963-56d2-82b0-d2a738997def"
    )
