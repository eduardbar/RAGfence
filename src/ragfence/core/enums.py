"""Canonical enums (TRD §3.1).

Pure value objects: str-based so they serialize to plain strings and validate
arbitrary input without any I/O.
"""

from enum import Enum


class Classification(str, Enum):
    """Document classification; rank orders public < internal < confidential < restricted."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @property
    def rank(self) -> int:
        return _CLASSIFICATION_RANK[self]


class DocumentStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScenarioOutcome(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    CRITICAL = "critical"


_CLASSIFICATION_RANK: dict[Classification, int] = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.CONFIDENTIAL: 2,
    Classification.RESTRICTED: 3,
}
