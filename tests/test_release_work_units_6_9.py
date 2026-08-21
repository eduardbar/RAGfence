"""Offline release-readiness contracts for work units 6-9."""

from pathlib import Path

from ragfence.release_readiness import audit, benchmark, checklist

ROOT = Path(__file__).parents[1]


def test_acme_benchmark_has_local_baseline_and_zero_leakage() -> None:
    result = benchmark.run_acme_benchmark()
    assert result["baseline"]["kind"] == "local_sanity_baseline"
    assert result["baseline"]["production_claim"] is False
    assert result["corpus_documents"] == 5
    assert result["query_count"] == 7
    assert result["errors"] == 0
    assert result["unauthorized_retrievals"] == 0
    assert result["search_ms"]["p95"] <= result["baseline"]["search_p95_ms"]


def test_audit_scans_tracked_text_without_returning_secret_values() -> None:
    result = audit.scan_repository(ROOT)
    assert result["scopes"] == ["tracked_text", "history_text", "lockfile", "wheel"]
    assert all("value" not in finding for finding in result["findings"])
    assert result["secret_values_exposed"] == 0
    assert result["dependency_audit"]["status"] in {"clean", "unavailable"}


def test_checklist_distinguishes_public_ci_from_local_blockers() -> None:
    result = checklist.validate(ROOT)
    assert result["checks"]["offline_workflows"]["status"] == "pass"
    assert result["checks"]["public_ci_receipt"]["status"] == "blocked_non_local"
    assert result["checks"]["public_ci_receipt"]["local_verdict_substitution"] is False
    assert result["release_ready"] is False


def test_both_workflows_are_included_in_checklist() -> None:
    result = checklist.validate(ROOT)
    assert result["checks"]["offline_workflows"]["workflows"] == [
        ".github/workflows/ci.yml",
        ".github/workflows/ragfence-test.yml",
    ]


def test_public_ci_receipt_unlocks_release_readiness() -> None:
    result = checklist.validate(
        ROOT,
        public_ci_receipt={
            "url": "https://github.com/eduardbar/RAGfence/actions/runs/32182933269",
            "sha": "c3798eae2d70590374d9492cffab563281941cfa",
            "conclusion": "success",
        },
    )

    assert result["checks"]["public_ci_receipt"]["status"] == "pass"
    assert result["release_ready"] is True


def test_audit_exempts_test_files_and_known_fixture_tokens() -> None:
    """Los fixtures deliberados de tests no son secretos: ni tracked ni history."""
    from ragfence.release_readiness.audit import _scan_text

    marker = 'MARKER_TOKEN = "supersecret-marker-token-7f3a"'

    # Un archivo bajo tests/ está exento aunque el scope lleve prefijo tracked:
    assert _scan_text(marker, r"tracked:tests\test_x.py") == []

    # El token fixture conocido en texto de historia tampoco es finding.
    assert _scan_text(marker, "history") == []
