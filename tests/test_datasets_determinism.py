"""Byte-identical regeneration and checksum goldens (PR 1, task 1.5).

Spec reference: openspec/changes/ragfence-acme-dataset/specs/synthetic-dataset/spec.md
- Byte-Identical Regeneration / Scenario: Regeneration equality
- Synthetic Document Corpus (checksum MUST be lowercase SHA-256 hex)
"""

from typing import Any

from ragfence.datasets import SEED, build_acme_corp
from ragfence.datasets.acme import AcmeCorpDataset, AcmeDocument
from ragfence.datasets.checksums import canonical_json, sha256_hex

CFO_PATH = "finance/payroll/cfo-payroll-summary.pdf"

# Derived from the fixed literal CFO paragraph pool with SEED (authored data).
CFO_BODY = (
    "Acme Corp FY2026 payroll summary prepared by the Office of the CFO for the "
    "board compensation review. Total annual payroll obligations are forecast at "
    "$18.4M across 412 employees, with the executive compensation package disclosed "
    "separately.\n\n"
    "The Chief Financial Officer's total compensation for FY2026 is $347,500, "
    "comprising a base salary of $250,000, a target bonus of $75,000, and a long-term "
    "equity grant valued at $22,500 at the time of award."
)
CFO_CHECKSUM = "32053524069bb1f18ba66da4d0cd2b7700afe730b9c267d05606b3770e341e12"

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _document(doc: AcmeDocument) -> dict[str, Any]:
    return {
        "id": str(doc.id),
        "path": doc.path,
        "title": doc.title,
        "source": doc.source,
        "checksum": doc.checksum,
        "classification": doc.classification.value,
        "status": doc.status.value,
        "body": doc.body,
        "acl": doc.acl.model_dump(mode="json"),
    }


def _snapshot(ds: AcmeCorpDataset) -> dict[str, Any]:
    return {
        "tenant": {"id": str(ds.tenant.id), "slug": ds.tenant.slug, "name": ds.tenant.name},
        "departments": {
            slug: {"id": str(d.id), "slug": d.slug, "name": d.name}
            for slug, d in ds.departments.items()
        },
        "groups": {
            slug: {"id": str(g.id), "slug": g.slug, "name": g.name} for slug, g in ds.groups.items()
        },
        "users": {
            email: {
                "id": str(u.id),
                "department_id": str(u.department_id),
                "email": u.email,
                "name": u.name,
                "classification": u.classification.value,
            }
            for email, u in ds.users.items()
        },
        "user_groups": sorted(
            (str(user_id), str(group_id)) for user_id, group_id in ds.user_groups
        ),
        "documents": {path: _document(doc) for path, doc in ds.documents.items()},
    }


def test_canonical_json_sorts_keys_compact_utf8() -> None:
    assert canonical_json({"b": 1, "a": [2]}) == b'{"a":[2],"b":1}'


def test_sha256_hex_is_lowercase_64_hex() -> None:
    digest = sha256_hex(b"")
    assert digest == EMPTY_SHA256
    assert len(digest) == 64
    assert digest == digest.lower()


def test_regeneration_is_byte_identical() -> None:
    first = build_acme_corp(SEED)
    second = build_acme_corp(SEED)
    first_bytes = canonical_json(_snapshot(first))
    second_bytes = canonical_json(_snapshot(second))
    assert first_bytes == second_bytes
    assert len(first_bytes) > 100  # non-trivial payload, not an empty snapshot


def test_cfo_body_matches_authored_literal() -> None:
    ds = build_acme_corp(SEED)
    assert ds.documents[CFO_PATH].body == CFO_BODY


def test_cfo_checksum_matches_golden_literal() -> None:
    ds = build_acme_corp(SEED)
    cfo = ds.documents[CFO_PATH]
    assert cfo.checksum == CFO_CHECKSUM
    assert len(cfo.checksum) == 64
    assert cfo.checksum == cfo.checksum.lower()
    assert cfo.checksum == sha256_hex(canonical_json(cfo.body))
