"""Deterministic token-count fallback shared by all LLM providers.

This intentionally is not a vendor tokenizer.  It counts UTF-8 code points after
normalizing line endings, which is stable offline and makes missing provider
usage explicit rather than silently inventing vendor-specific counts.
"""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Return a deterministic non-negative estimate for *text*.

    The estimator is deliberately conservative and dependency-free.  Its exact
    semantics are part of the fake/offline contract, not an assertion about a
    vendor's tokenizer.
    """
    return len(text.replace("\r\n", "\n").replace("\r", "\n"))


def estimate_prompt_tokens(contents: list[str]) -> int:
    """Estimate prompt tokens as the sum of per-message content estimates."""
    return sum(estimate_tokens(content) for content in contents)
