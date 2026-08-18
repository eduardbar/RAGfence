"""Attack scenario catalog contract tests."""

from ragfence.attacks.scenarios import scenario_catalog

EXPECTED_IDS = (
    "cross-tenant-retrieval",
    "cross-department-retrieval",
    "direct-sensitive-data",
    "metadata-spoofing",
    "prompt-injection",
    "indirect-prompt-injection",
    "document-poisoning",
    "role-escalation",
    "deleted-document-retrieval",
    "retrieval-filter-bypass",
)


def test_catalog_contains_exactly_the_prd_scenarios() -> None:
    scenarios = scenario_catalog()

    assert tuple(item.id for item in scenarios) == EXPECTED_IDS
    assert len({item.id for item in scenarios}) == 10


def test_catalog_entries_declare_execution_contract() -> None:
    for scenario in scenario_catalog():
        assert scenario.name
        assert scenario.description
        assert scenario.target_stage in {"retrieval", "generation", "both"}
        assert scenario.expected_behavior in {"must_block", "must_allow"}
