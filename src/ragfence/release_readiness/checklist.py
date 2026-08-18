"""Release checklist validator with explicit local/non-local classifications."""

from __future__ import annotations

import re
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


def _public_ci_check(receipt: dict[str, str] | None) -> dict[str, Any]:
    if receipt is None:
        return {
            "status": "blocked_non_local",
            "reason": (
                "No public GitHub run receipt was supplied; local checks cannot substitute for it."
            ),
            "local_verdict_substitution": False,
        }
    url = receipt.get("url", "")
    sha = receipt.get("sha", "")
    conclusion = receipt.get("conclusion", "")
    valid = (
        url.startswith("https://github.com/")
        and bool(re.fullmatch(r"[0-9a-f]{40}", sha))
        and conclusion == "success"
    )
    return {
        "status": "pass" if valid else "blocked_non_local",
        "url": url,
        "sha": sha,
        "conclusion": conclusion,
        "local_verdict_substitution": False,
    }


def validate(root: Path, *, public_ci_receipt: dict[str, str] | None = None) -> dict[str, Any]:
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
        "public_ci_receipt": _public_ci_check(public_ci_receipt),
    }
    release_ready = all(item["status"] == "pass" for item in checks.values())
    return {"release_ready": release_ready, "checks": checks}
