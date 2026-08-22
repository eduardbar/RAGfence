"""Qdrant-backed vector retrieval with payload ACL pre-filtering.

Qdrant points use a payload schema parallel to the typed database ACL columns:
``tenant_id`` and ``department_id`` are UUID strings, ``classification`` is the
integer classification rank (public=0 through restricted=3), ``allowed_user_ids``
and ``allowed_group_ids`` are UUID-string lists, ``deleted_at`` is an ISO
8601 timestamp or ``None``, and ``status`` is the lowercase document-status
value. The remaining payload fields are ``document_id``, ``title``,
``chunk_index``, ``content``, and ``chunk_metadata``.

The core ``VectorStore`` protocol accepts a SQLAlchemy ``policy_predicate`` for
its pgvector implementation. That predicate is SQL-specific and cannot be
translated or evaluated safely by Qdrant, so this adapter deliberately does
not consume it: a SQL-only ``search`` call raises ``NotImplementedError`` and
callers use ``search_with_context`` instead. An explicitly translated Qdrant
``filter`` can also be passed to ``search``. ``build_qdrant_filter`` translates the
server-derived ``AuthorizationContext`` into a Qdrant ``Filter``. All ACL,
soft-delete, and status checks are therefore Qdrant pre-filters; this adapter
never performs post-hoc Python authorization filtering (ADR-3).
"""

# qdrant-client is an optional extra; its imports are checked when that extra is installed.
# mypy: disable-error-code=import-not-found

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import ColumnElement

from ragfence.core.models import AuthorizationContext, RetrievedChunk

if TYPE_CHECKING:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter


def build_qdrant_filter(ctx: AuthorizationContext) -> Filter:
    """Build the Qdrant payload filter equivalent to ``build_acl_predicate``.

    Classification is stored as its integer rank, making the clearance check a
    payload range condition. Access is deny-by-default: a point must match the
    actor's tenant and clearance and at least one of public, direct-user,
    group, or department grants. Active, READY documents are also required.
    """
    from qdrant_client.models import (
        FieldCondition,
        Filter,
        IsNullCondition,
        MatchAny,
        MatchValue,
        PayloadField,
        Range,
    )

    access_grants: list[Any] = [
        FieldCondition(key="classification", match=MatchValue(value=0)),
        FieldCondition(key="allowed_user_ids", match=MatchValue(value=str(ctx.user_id))),
    ]
    if ctx.allowed_group_ids:
        access_grants.append(
            FieldCondition(
                key="allowed_group_ids",
                match=MatchAny(any=[str(group_id) for group_id in ctx.allowed_group_ids]),
            )
        )
    if ctx.department_id is not None:
        access_grants.append(
            FieldCondition(key="department_id", match=MatchValue(value=str(ctx.department_id)))
        )

    return Filter(
        must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=str(ctx.tenant_id))),
            FieldCondition(key="classification", range=Range(lte=ctx.classification.rank)),
            FieldCondition(key="status", match=MatchValue(value="ready")),
            IsNullCondition(is_null=PayloadField(key="deleted_at")),
        ],
        should=access_grants,
    )


class QdrantVectorStore:
    """VectorStore adapter that applies authorization in Qdrant payload filters."""

    def __init__(self, client: QdrantClient, collection_name: str = "ragfence_chunks") -> None:
        self._client = client
        self._collection_name = collection_name

    def search(
        self,
        *,
        embedding: list[float],
        policy_predicate: ColumnElement[bool],
        top_k: int,
        filter: Filter | None = None,
    ) -> list[RetrievedChunk]:
        """Search with an explicit Qdrant filter, rejecting SQL-only calls.

        ``filter`` is the translated, server-derived authorization filter. It
        is optional only to preserve the core protocol's call shape; omitting
        it raises rather than accidentally running an unfiltered search.
        """
        if filter is None:
            raise NotImplementedError(
                "QdrantVectorStore does not consume SQL policy_predicate; "
                "call search_with_context(embedding=..., ctx=..., top_k=...)"
            )
        return self._search(embedding=embedding, payload_filter=filter, top_k=top_k)

    def search_with_context(
        self, *, embedding: list[float], ctx: AuthorizationContext, top_k: int
    ) -> list[RetrievedChunk]:
        """Return authorized READY chunks ranked by Qdrant cosine similarity.

        Qdrant's cosine score is the cosine similarity (equivalent to the
        database adapter's ``1 - distance``), so it is copied unchanged.
        """
        return self._search(
            embedding=embedding,
            payload_filter=build_qdrant_filter(ctx),
            top_k=top_k,
        )

    def _search(
        self, *, embedding: list[float], payload_filter: Filter, top_k: int
    ) -> list[RetrievedChunk]:
        query_points = getattr(self._client, "query_points", None)
        if query_points is not None:
            response = query_points(
                collection_name=self._collection_name,
                query=embedding,
                query_filter=payload_filter,
                limit=top_k,
                with_payload=True,
            )
            points = response.points
        else:
            search = getattr(self._client, "search")  # noqa: B009 - compatibility with qdrant 1.9
            points = search(
                collection_name=self._collection_name,
                query_vector=embedding,
                query_filter=payload_filter,
                limit=top_k,
                with_payload=True,
            )

        return [_retrieved_chunk(point) for point in points]


def _retrieved_chunk(point: Any) -> RetrievedChunk:
    """Convert a Qdrant scored point to the canonical retrieval model."""
    payload = dict(point.payload or {})
    return RetrievedChunk(
        chunk_id=UUID(str(point.id)),
        document_id=UUID(str(payload["document_id"])),
        document_title=str(payload["title"]),
        chunk_index=int(payload["chunk_index"]),
        content=str(payload["content"]),
        score=float(point.score),
        metadata=dict(payload.get("chunk_metadata") or {}),
    )
