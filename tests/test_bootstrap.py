"""Import smoke tests for the installable package skeleton (tasks 1.1-1.2).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- Packaging Contract / Scenario: Editable install and import.
"""

import importlib

import ragfence

# Canonical subpackages per TRD Section 2 (11 total).
SUB_PACKAGES = [
    "core",
    "policies",
    "providers",
    "cli",
    "db",
    "auth",
    "retrieval",
    "evaluation",
    "attacks",
    "adapters",
    "observability",
]


def test_package_imports() -> None:
    assert ragfence.__name__ == "ragfence"


def test_version_string_present() -> None:
    assert ragfence.__version__ == "0.1.0"


def test_all_subpackages_import() -> None:
    for name in SUB_PACKAGES:
        module = importlib.import_module(f"ragfence.{name}")
        assert module.__name__ == f"ragfence.{name}"
