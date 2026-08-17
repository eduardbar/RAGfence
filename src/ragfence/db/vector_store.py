"""DB-backed ``VectorStore`` over pgvector (spec req 6, ADR-3).

Retrieves over ``document_chunks`` joined to ``document_acl`` and ``documents``,
applying the shared access predicate as a single SQL pre-filter. The predicate
is ``build_acl_predicate`` (typed ACL columns only — never the JSONB ``metadata``
column); row-state exclusions (soft-deleted, non-READY) are also enforced in SQL
so a deleted, pending, or cross-tenant chunk can never leak. Ranking is cosine
distance via the pgvector ``<=>`` operator; the returned ``score`` is the cosine
similarity (``1 - distance``). No post-hoc Python filtering (ADR-3).
"""

from __future__ import annotations

from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import ColumnElement, cast, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ragfence.core.enums import DocumentStatus
from ragfence.core.models import RetrievedChunk
from ragfence.db.models import Document, DocumentACL, DocumentChunk

# Embedding dimension for the corpus (BACKEND_SCHEMA: ``vector(1536)``).
_EMBEDDING_DIM = 1536


class DbVectorStore:
    """Conforms to the ``VectorStore`` protocol; search applies the predicate in SQL."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self, *, embedding: list[float], policy_predicate: ColumnElement[bool], top_k: int
    ) -> list[RetrievedChunk]:
        """Return up to ``top_k`` ACL-allowed, active, ready chunks by cosine similarity.

        The ``policy_predicate`` (the shared ACL gate) is applied as a WHERE
        clause on the join — never consulted after the query. Cosine distance
        ``<=>`` orders rows ascending (closest match first).
        """
        distance = DocumentChunk.embedding.cosine_distance(cast(embedding, Vector(_EMBEDDING_DIM)))
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                Document.title,
                DocumentChunk.chunk_index,
                DocumentChunk.content,
                DocumentChunk.chunk_metadata,
                (1 - distance).label("score"),
            )
            .join(DocumentACL, DocumentACL.document_id == DocumentChunk.document_id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                policy_predicate,
                Document.deleted_at.is_(None),
                Document.status == DocumentStatus.READY,
                DocumentChunk.embedding.isnot(None),
            )
            .order_by(distance)
            .limit(top_k)
        )
        with Session(self._engine) as session:
            rows = session.execute(stmt).all()

        chunks: list[RetrievedChunk] = []
        for chunk_id, document_id, title, chunk_index, content, metadata, score in rows:
            chunks.append(
                RetrievedChunk(
                    chunk_id=UUID(str(chunk_id)),
                    document_id=UUID(str(document_id)),
                    document_title=str(title),
                    chunk_index=int(chunk_index),
                    content=str(content),
                    score=float(score),
                    metadata=dict(metadata or {}),
                )
            )
        return chunks
