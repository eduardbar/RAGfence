"""Release checklist validator with explicit local/non-local classifications."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .audit import scan_repository
from .benchmark import run_acme_benchmark


def _workflow_check(root: Path) -> dict[str, Any]:
    paths = [".github/workflows/ci.yml", ".github/workflows/ragfence-test.yml"]
    missing = [path for path in paths if not (root / path).is_file()]
    text = "\n".join(
        (root / path).read_text(encoding="utf-8") for path in paths if (root / path).is_file()
    )
    required = (
        "ruff check",
        "mypy",
        "pytest",
        "workflow_call",
        "ragfence init",
        "ragfence test",
        "Final gate",
    )
    absent = [item for item in required if item.lower() not in text.lower()]
    return {
        "status": "pass" if not missing and not absent else "fail",
        "workflows": paths,
        "missing": missing + absent,
    }


def validate(root: Path) -> dict[str, Any]:
    benchmark = run_acme_benchmark()
    audit = scan_repository(root)
    checks = {
        "offline_workflows": _workflow_check(root),
        "acme_benchmark": {
            "status": "pass"
            if benchmark["errors"] == 0 and benchmark["unauthorized_retrievals"] == 0
            else "fail"
        },
        "audit": {
            "status": "pass" if not audit["findings"] else "fail",
            "dependency": audit["dependency_audit"],
        },
        "public_ci_receipt": {
            "status": "blocked_non_local",
            "reason": (
                "No public GitHub run receipt was supplied; local checks cannot substitute for it."
            ),
            "local_verdict_substitution": False,
        },
    }
    release_ready = all(item["status"] == "pass" for item in checks.values())
    return {"release_ready": release_ready, "checks": checks}
