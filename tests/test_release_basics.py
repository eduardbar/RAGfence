"""Release basics validation (task 1.6).

Spec reference: openspec/changes/ragfence-foundation/specs/project-bootstrap/spec.md
- Release Basics / Scenario: No secrets in template — placeholders only, no real credentials.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = ["LICENSE", "README.md", "CONTRIBUTING.md", ".env.example", ".gitignore"]

PLACEHOLDER_MARKERS = ("CHANGEME", "your-", "example", "xxxx", "placeholder", "<")

CREDENTIAL_KEYS = ("KEY", "PASSWORD", "TOKEN", "SECRET")

REAL_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI-style secret key
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),  # GitHub personal access token
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack token
]


def _looks_like_secret(value: str) -> bool:
    if any(marker in value for marker in PLACEHOLDER_MARKERS):
        return False
    if any(pattern.search(value) for pattern in REAL_SECRET_PATTERNS):
        return True
    return len(value) >= 24


def test_required_release_files_exist() -> None:
    for name in REQUIRED_FILES:
        assert (ROOT / name).is_file(), f"missing required file {name}"


def test_env_example_values_are_placeholders() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    entries = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert entries, ".env.example must declare at least one variable"
    for entry in entries:
        assert "=" in entry, f"malformed entry: {entry!r}"
        key, _, value = entry.partition("=")
        key = key.strip()
        value = value.strip()
        assert key, f"empty key in {entry!r}"
        assert not _looks_like_secret(value), f"{key} carries a real-looking secret"
        if any(tag in key.upper() for tag in CREDENTIAL_KEYS):
            assert any(marker in value for marker in PLACEHOLDER_MARKERS), (
                f"{key} must hold a placeholder, got {value!r}"
            )


def test_no_real_secrets_in_repo_texts() -> None:
    for name in ("README.md", "CONTRIBUTING.md", ".env.example"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for pattern in REAL_SECRET_PATTERNS:
            assert not pattern.search(text), f"{name} matched {pattern.pattern!r}"


def test_gitignore_ignores_dot_env_but_keeps_template() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content
    assert "!.env.example" in content


def test_license_is_apache_2() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0, January 2004" in text
