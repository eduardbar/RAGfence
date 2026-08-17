"""Citation assembly for secure retrieval (spec req 4, ADR-4/5).

Yields exactly one ``Citation`` per ``RetrievedChunk`` carrying document
provenance — ``title``, ``source``, ``checksum``, ``chunk_index``, ``score`` —
with the ``snippet`` truncated to a redaction-safe length (default ~200 chars)
while the full content stays on the ``RetrievedChunk`` for internal use.

``source``/``checksum`` are resolved from the document row at citation time
(design Open Question: never stored on the chunk). The meta object is duck-typed:
``build_citations`` reads ``.source``/``.checksum`` via ``getattr`` so a document
row without those attributes degrades to ``None`` rather than failing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any
from uuid import UUID

from ragfence.core.models import Citation, RetrievedChunk

# Redaction-safe snippet length (design ADR-5: ~200 chars).
SNIPPET_LIMIT = 200


def truncate(text: str, *, limit: int = SNIPPET_LIMIT) -> str:
    """Truncate ``text`` to ``limit`` characters (no mid-word splitting needed)."""
    return text if len(text) <= limit else text[:limit]


DocumentMetaLoader = Callable[[UUID], Any | None]


def build_citations(
    chunks: Iterable[RetrievedChunk],
    document_meta: DocumentMetaLoader | None = None,
) -> list[Citation]:
    """Assemble one truncated-provenance ``Citation`` per retrieved chunk."""
    loader = document_meta or (lambda _did: None)
    citations: list[Citation] = []
    for chunk in chunks:
        meta = loader(chunk.document_id)
        citations.append(
            Citation(
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                chunk_index=chunk.chunk_index,
                snippet=truncate(chunk.content),
                source=getattr(meta, "source", None),
                checksum=getattr(meta, "checksum", None),
                score=chunk.score,
            )
        )
    return citations
