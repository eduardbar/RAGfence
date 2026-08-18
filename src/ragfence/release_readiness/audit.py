"""Secret-safe local dependency and repository audit harness."""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any

_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret|password|passwd|token|authorization|bearer|dsn)"
    r"\s*[:=]\s*['\"]([^'\"\s]{8,})['\"]"
)


def _scan_text(text: str, scope: str) -> list[dict[str, str]]:
    findings = []
    for match in _SECRET.finditer(text):
        value = match.group(1)
        lower = value.lower()
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
