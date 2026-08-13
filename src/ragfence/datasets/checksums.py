"""Canonical JSON and SHA-256 helpers for dataset checksums (PR 1).

Canonical form: compact UTF-8 JSON with sorted keys and no whitespace
(``sort_keys`` + ``separators``), so identical logical data always produces
identical bytes and therefore identical checksums (design: Checksums decision;
BACKEND_SCHEMA section 1).
"""

import hashlib
import json
from typing import Any


def canonical_json(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical compact UTF-8 JSON bytes.

    Keys are sorted recursively; ``ensure_ascii=False`` keeps non-ASCII text as
    UTF-8 so the byte output is the UTF-8 representation of the content.
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()
