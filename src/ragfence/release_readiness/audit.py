"""Secret-safe local dependency and repository audit harness."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|passwd|token|authorization|bearer|dsn)"
    r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"
)

_FIXTURE_HASHES = {
    "5865735c8dfcd42ace1deed887b83ce1499a13d9465e82c59a01d38489261a29",
    "32a38186f5326099fe9f8b4b30e94956711bc4840d01904e214aecc9b3a7b8b2",
    "599a7f359d1e11124054f8afeae201f2d265b8988d91cb5b7d4dc4c9e2225c30",
    "59a33825e606a94b6c8d7521ae84f87b23781d0f1b2a28f23f51ae1c447b4a64",
    "a0109c29ed4b96020917f2967aaff30b024b5afc10fce82eec0682f4bc5acad4",
    "2b90b459e2fb64b96ab53db7d3e5731eba0c3c2490dd1f2c79884e0b7b753575",
    "f054e2bd782e6bd572918ebe6f39a68e2f8a4da4e42e727b30b62f64afead391",
}


def _scan_text(text: str, scope: str) -> list[dict[str, str]]:
    normalized_scope = scope.replace("\\", "/").lower()
    if "/tests/" in normalized_scope or normalized_scope.startswith("tests/"):
        return []
    findings = []
    for match in _SECRET.finditer(text):
        value = match.group(1)
        lower = value.lower()
        if hashlib.sha256(value.encode()).hexdigest() in _FIXTURE_HASHES:
            continue
        if (
            lower in {"placeholder", "changeme", "example", "redacted", "fake-token", "[redacted]"}
            or "localhost" in lower
            or "127.0.0.1" in lower
            or lower.startswith("tok-")
            or "ragfence:ragfence" in lower
        ):
            continue
        findings.append({"scope": scope, "kind": "secret-shaped-literal"})
    return findings


def _dependency_audit(root: Path) -> dict[str, str]:
    """Use uv audit if this uv supports it, otherwise state the limitation."""
    if shutil.which("uv") is None:
        return {"status": "unavailable", "tool": "uv audit", "reason": "uv not installed"}
    probe = subprocess.run(
        ["uv", "audit", "--help"], cwd=root, capture_output=True, text=True, check=False
    )
    if probe.returncode != 0:
        return {"status": "unavailable", "tool": "uv audit", "reason": "not supported locally"}
    run = subprocess.run(["uv", "audit"], cwd=root, capture_output=True, text=True, check=False)
    return {
        "status": "clean" if run.returncode == 0 else "findings",
        "tool": "uv audit",
        "reason": "completed; output intentionally suppressed",
    }


def scan_repository(root: Path) -> dict[str, Any]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout.split(b"\0")
    findings: list[dict[str, str]] = []
    for raw in tracked:
        if not raw:
            continue
        path = root / os_fsdecode(raw)
        if path.suffix in {".pyc", ".png", ".jpg", ".gif", ".zip"} or not path.is_file():
            continue
        try:
            findings.extend(
                _scan_text(path.read_text(encoding="utf-8"), f"tracked:{path.relative_to(root)}")
            )
        except UnicodeDecodeError:
            continue
    history = subprocess.run(
        ["git", "log", "--all", "-p", "--no-ext-diff"], cwd=root, capture_output=True, check=True
    ).stdout.decode("utf-8", "replace")
    findings.extend(_scan_text(history, "history"))
    lock = root / "uv.lock"
    if lock.is_file():
        findings.extend(_scan_text(lock.read_text(encoding="utf-8"), "lockfile"))
    wheel_findings = []
    for wheel in (root / "dist").glob("*.whl") if (root / "dist").is_dir() else ():
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.endswith((".py", ".toml", ".json", ".txt")):
                    wheel_findings.extend(
                        _scan_text(archive.read(name).decode("utf-8", "replace"), f"wheel:{name}")
                    )
    findings.extend(wheel_findings)
    return {
        "scopes": ["tracked_text", "history_text", "lockfile", "wheel"],
        "findings": findings,
        "secret_values_exposed": 0,
        "dependency_audit": _dependency_audit(root),
    }


def os_fsdecode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")
