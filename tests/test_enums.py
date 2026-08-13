"""Canonical enum tests (task 2.1).

Spec reference: openspec/changes/ragfence-foundation/specs/domain-models/spec.md
- Canonical Enums / Scenario: Enum member values and ordering
- Canonical Enums / Scenario: Unknown member rejected
"""

import pytest

from ragfence.core.enums import Classification, DocumentStatus, FindingSeverity, ScenarioOutcome


def test_classification_member_values() -> None:
    assert Classification.PUBLIC.value == "public"
    assert Classification.INTERNAL.value == "internal"
    assert Classification.CONFIDENTIAL.value == "confidential"
    assert Classification.RESTRICTED.value == "restricted"


def test_document_status_member_values() -> None:
    assert DocumentStatus.PENDING.value == "pending"
    assert DocumentStatus.READY.value == "ready"
    assert DocumentStatus.FAILED.value == "failed"


def test_finding_severity_member_values() -> None:
    assert FindingSeverity.LOW.value == "low"
    assert FindingSeverity.MEDIUM.value == "medium"
    assert FindingSeverity.HIGH.value == "high"
    assert FindingSeverity.CRITICAL.value == "critical"


def test_scenario_outcome_member_values() -> None:
    assert ScenarioOutcome.PASS.value == "pass"
    assert ScenarioOutcome.WARNING.value == "warning"
    assert ScenarioOutcome.FAIL.value == "fail"
    assert ScenarioOutcome.CRITICAL.value == "critical"


def test_classification_rank_ordering() -> None:
    ordered = [
        Classification.PUBLIC,
        Classification.INTERNAL,
        Classification.CONFIDENTIAL,
        Classification.RESTRICTED,
    ]
    assert [member.rank for member in ordered] == [0, 1, 2, 3]


@pytest.mark.parametrize("value", ["top_secret", "classified", ""])
def test_unknown_classification_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        Classification(value)
