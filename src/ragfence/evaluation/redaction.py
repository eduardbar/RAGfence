"""Shared, deterministic evidence redaction primitives for evaluation output."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

REDACTION_TOKEN = "[REDACTED]"
DEFAULT_MAX_TEXT = 512
_SENSITIVE_KEYS = {
    "authorization",
    "authorization_header",
    "content",
    "chunk_content",
    "api_key",
    "api-key",
    "apikey",
    "x-api-key",
    "token",
    "access_token",
    "password",
    "secret",
    "raw_content",
}
_SECRET_PATTERN = re.compile(
    r"(?ix)(bearer\s+|basic\s+|token\s+|password\s*[=:]\s*|"
    r"api[-_ ]?key\s*[=:]\s*|x-api-key\s*[=:]\s*)"
    r"[^\s,;]+"
)


def safe_id(value: object) -> str:
    """Return a stable identifier representation without exposing object contents."""
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def safe_hash(value: object) -> str:
    """Return a full SHA-256 digest suitable for reproducible evidence."""
    return hashlib.sha256(str(value).encode("utf-8", errors="replace")).hexdigest()


def bounded_text(
    value: object,
    *,
    max_length: int = DEFAULT_MAX_TEXT,
    markers: Sequence[str] = (),
) -> str:
    """Redact secrets/markers and bound text to ``max_length`` characters."""
    if max_length < 1:
        return ""
    text = str(value)
    text = _SECRET_PATTERN.sub(r"\1" + REDACTION_TOKEN, text)
    for marker in markers:
        if marker:
            text = re.sub(re.escape(marker), REDACTION_TOKEN, text, flags=re.IGNORECASE)
    if len(text) <= max_length:
        return text
    if max_length == 1:
        return "…"
    return text[: max_length - 1] + "…"


def redact_evidence(
    value: object,
    *,
    max_text: int = DEFAULT_MAX_TEXT,
    markers: Sequence[str] = (),
    _key: str | None = None,
) -> Any:
    """Recursively redact secret fields, secret strings, markers, and long text."""
    if _key is not None and _key.casefold() in _SENSITIVE_KEYS:
        return REDACTION_TOKEN
    if isinstance(value, Mapping):
        return {
            str(key): redact_evidence(item, max_text=max_text, markers=markers, _key=str(key))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_evidence(item, max_text=max_text, markers=markers) for item in value]
    if isinstance(value, (str, bytes)):
        return bounded_text(
            value.decode() if isinstance(value, bytes) else value,
            max_length=max_text,
            markers=markers,
        )
    return value


def redact_secrets(text: str, secrets: Sequence[str]) -> str:
    """Replace every occurrence of each secret in ``text`` with REDACTION_TOKEN.

    Used by the adapter error boundary to ensure bearer tokens or other
    dynamic secrets never leak through exception messages, reason strings,
    or log lines (spec R4.2 secrets hygiene).
    """
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, REDACTION_TOKEN)
    return result
