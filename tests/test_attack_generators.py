"""Deterministic attack case generation tests."""

import pytest

from ragfence.attacks.generators import bounded_top_k, generate_cases, validate_filters
from ragfence.attacks.scenarios import scenario_catalog
from ragfence.datasets.acme import build_acme_corp, build_globex_corp


def test_same_seed_produces_byte_equal_cases() -> None:
    first = [case.model_dump_json() for case in generate_cases(seed=42)]
    second = [case.model_dump_json() for case in generate_cases(seed=42)]

    assert first == second
    assert [case.id for case in generate_cases(seed=42)] == [
        case.id for case in generate_cases(seed=42)
    ]


def test_cases_have_valid_synthetic_actors_and_expected_behavior() -> None:
    scenarios = {scenario.id: scenario for scenario in scenario_catalog()}

    for case in generate_cases():
        scenario = scenarios[case.scenario_id]
        assert case.actor.is_authenticated is True
        assert case.actor.source == "synthetic"
        assert case.expected_allow is (scenario.expected_behavior == "must_allow")


def test_cases_use_scenario_specific_acme_actors_and_structured_options() -> None:
    cases = {case.scenario_id: case for case in generate_cases()}

    assert (
        cases["cross-department-retrieval"].actor.department_id
        != cases["role-escalation"].actor.department_id
    )
    for case in cases.values():
        assert case.metadata.scenario_id == case.scenario_id
        assert case.retrieval_options.document_id
        assert set(case.retrieval_options.filters) == {"document_id"}


def test_cross_tenant_case_uses_an_actor_outside_the_target_document_tenant() -> None:
    case = next(case for case in generate_cases() if case.scenario_id == "cross-tenant-retrieval")
    target = build_acme_corp().documents[case.metadata.target_document]
    persisted_actor = build_globex_corp().context_for(case.metadata.actor_email)

    assert case.actor.is_authenticated is True
    assert case.actor.tenant_id != target.tenant_id
    assert case.retrieval_options.document_id == target.id
    assert case.actor == persisted_actor


def test_filter_bypass_top_k_is_bounded() -> None:
    assert bounded_top_k(-10) == 1
    assert bounded_top_k(10) == 10
    assert bounded_top_k(10_000) == 50


def test_filter_bypass_rejects_arbitrary_filters() -> None:
    with pytest.raises(ValueError, match="filters"):
        validate_filters({"where": "1=1"})


def test_validate_filters_accepts_only_typed_document_id() -> None:
    document_id = generate_cases()[0].retrieval_options.document_id

    assert validate_filters({"document_id": document_id}) == {"document_id": document_id}

    with pytest.raises(ValueError, match="document_id"):
        validate_filters({"document_id": "1 OR 1=1"})
