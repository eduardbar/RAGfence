"""RED contract for the production declarative evaluation-control matrix."""

from ragfence.attacks.generators import (
    ExpectedBehavior,
    default_evaluation_controls,
)
from ragfence.datasets.acme import build_acme_corp, build_globex_corp


def test_default_matrix_is_deterministic_and_self_describing() -> None:
    first = default_evaluation_controls()
    second = default_evaluation_controls()

    assert first == second
    assert [control.id for control in first] == [control.id for control in second]
    assert {control.id for control in first} >= {
        "same-tenant-authorized",
        "same-tenant-no-permission",
        "cross-tenant",
        "cross-department",
        "explicit-allowlist",
        "soft-deleted-document",
        "public-same-tenant",
        "insufficient-clearance",
    }
    for control in first:
        assert control.actor_email
        assert control.actor_tenant
        assert control.target_document
        assert control.prompt
        assert control.category
        assert isinstance(control.identity_required, bool)
        assert isinstance(control.retrieval_evidence_required, bool)
        assert isinstance(control.required_for_gate, bool)


def test_default_matrix_has_required_positive_and_negative_coverage() -> None:
    controls = {control.id: control for control in default_evaluation_controls()}

    assert {
        control_id
        for control_id, control in controls.items()
        if control.required_for_gate and control.expected_behavior.name == "MUST_ALLOW"
    } >= {"same-tenant-authorized", "explicit-allowlist", "public-same-tenant"}
    assert {
        control_id
        for control_id, control in controls.items()
        if control.required_for_gate and control.expected_behavior.name == "MUST_BLOCK"
    } >= {
        "same-tenant-no-permission",
        "cross-tenant",
        "cross-department",
        "soft-deleted-document",
        "insufficient-clearance",
    }


def test_expected_behavior_is_str_enum_with_canonical_members() -> None:
    assert issubclass(ExpectedBehavior, str)
    assert ExpectedBehavior.MUST_ALLOW == "must_allow"
    assert ExpectedBehavior.MUST_BLOCK == "must_block"
    assert ExpectedBehavior.MUST_ALLOW.name == "MUST_ALLOW"
    assert ExpectedBehavior.MUST_BLOCK.name == "MUST_BLOCK"
    assert set(ExpectedBehavior.__members__) == {"MUST_ALLOW", "MUST_BLOCK"}

    for control in default_evaluation_controls():
        assert isinstance(control.expected_behavior, ExpectedBehavior)


def test_control_ids_are_unique_and_canonical() -> None:
    controls = list(default_evaluation_controls())
    ids = [c.id for c in controls]

    assert len(ids) == len(set(ids))
    assert len(controls) == 8
    assert set(ids) == {
        "same-tenant-authorized",
        "same-tenant-no-permission",
        "cross-tenant",
        "cross-department",
        "explicit-allowlist",
        "soft-deleted-document",
        "public-same-tenant",
        "insufficient-clearance",
    }


def test_control_fixtures_reference_existing_actors_and_documents() -> None:
    acme = build_acme_corp()
    globex = build_globex_corp()
    tenant_datasets = {"acme-corp": acme, "globex-corp": globex}

    for control in default_evaluation_controls():
        dataset = tenant_datasets[control.actor_tenant]
        assert control.actor_email in dataset.users, (
            f"actor {control.actor_email} missing in tenant {control.actor_tenant}"
        )
        assert control.target_document in acme.documents, (
            f"target document {control.target_document} missing in acme corpus"
        )


def test_control_order_is_stable_and_declared() -> None:
    expected_order = (
        "same-tenant-authorized",
        "same-tenant-no-permission",
        "cross-tenant",
        "cross-department",
        "explicit-allowlist",
        "soft-deleted-document",
        "public-same-tenant",
        "insufficient-clearance",
    )
    assert tuple(c.id for c in default_evaluation_controls()) == expected_order
    assert tuple(c.id for c in default_evaluation_controls(seed=42)) == expected_order
