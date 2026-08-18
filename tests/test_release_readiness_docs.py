"""Offline release-readiness checks for public documentation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MARKDOWN = [
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    *sorted((ROOT / "docs").glob("*.md")),
]


def test_public_markdown_links_resolve_without_network() -> None:
    missing: list[str] = []
    for document in PUBLIC_MARKDOWN:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "unresolved documentation links: " + ", ".join(missing)


def test_readme_exposes_current_quickstart_and_release_links() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "foundation bootstrap" not in text.lower()
    for command in ("ragfence --help", "ragfence init", "ragfence test", ".ragfence/reports"):
        assert command in text
    for meaning in ("0 =", "1 =", "2 ="):
        assert meaning in text
    for link in ("CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md", "docs/README.md"):
        assert f"]({link})" in text
    assert "without Docker" in text
    assert "optional" in text.lower()


def test_docs_use_frozen_canonical_contract() -> None:
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_MARKDOWN)
    assert "GenericHTTPAdapter" in corpus
    assert "generic_http" in corpus
    assert "ragfence.toml" in corpus
    assert ".ragfence/reports" in corpus
    assert "0 =" in corpus and "1 =" in corpus and "2 =" in corpus
    assert "Docker" in corpus
    assert "offline" in corpus.lower()
