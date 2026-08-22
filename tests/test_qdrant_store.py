"""Qdrant vector-store ACL and row-state filtering tests."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

pytest.importorskip("qdrant_client")

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext
from ragfence.db.qdrant_store import QdrantVectorStore

_DIMENSION = 2
_TENANT_ACME = UUID("00000000-0000-0000-0000-000000000001")
_TENANT_GLOBEX = UUID("00000000-0000-0000-0000-000000000002")
_DEPARTMENT_ENGINEERING = UUID("00000000-0000-0000-0000-000000000010")
_USER_ALICE = UUID("00000000-0000-0000-0000-000000000020")
_GROUP_RESEARCH = UUID("00000000-0000-0000-0000-000000000030")


def _context(
    *,
    tenant_id: UUID = _TENANT_ACME,
    classification: Classification = Classification.INTERNAL,
    department_id: UUID | None = _DEPARTMENT_ENGINEERING,
    user_id: UUID = _USER_ALICE,
    groups: set[UUID] | None = None,
) -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=tenant_id,
        user_id=user_id,
        department_id=department_id,
        classification=classification,
        allowed_user_ids=set(),
        allowed_group_ids=groups or set(),
        is_authenticated=True,
        source="synthetic",
    )


def _point(
    name: str,
    vector: list[float],
    *,
    tenant_id: UUID = _TENANT_ACME,
    classification: Classification = Classification.INTERNAL,
    department_id: UUID | None = None,
    allowed_user_ids: list[UUID] | None = None,
    allowed_group_ids: list[UUID] | None = None,
    deleted_at: str | None = None,
    status: str = "ready",
) -> PointStruct:
    return PointStruct(
        id=uuid4(),
        vector=vector,
        payload={
            "tenant_id": str(tenant_id),
            "department_id": str(department_id) if department_id else None,
            "classification": classification.rank,
            "allowed_user_ids": [str(value) for value in allowed_user_ids or []],
            "allowed_group_ids": [str(value) for value in allowed_group_ids or []],
            "deleted_at": deleted_at,
            "status": status,
            "document_id": str(uuid4()),
            "title": name,
            "chunk_index": 0,
            "content": name,
            "chunk_metadata": {"source": name},
        },
    )


@pytest.fixture
def seeded_store() -> tuple[QdrantVectorStore, dict[str, UUID]]:
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="chunks",
        vectors_config=VectorParams(size=_DIMENSION, distance=Distance.COSINE),
    )
    points = [
        _point("acme-public", [1.0, 0.0], classification=Classification.PUBLIC),
        _point(
            "acme-user",
            [0.8, 0.6],
            allowed_user_ids=[_USER_ALICE],
        ),
        _point(
            "acme-group",
            [0.6, 0.8],
            allowed_group_ids=[_GROUP_RESEARCH],
        ),
        _point(
            "acme-department",
            [0.0, 1.0],
            department_id=_DEPARTMENT_ENGINEERING,
        ),
        _point(
            "acme-restricted",
            [0.99, 0.1],
            classification=Classification.RESTRICTED,
            allowed_user_ids=[_USER_ALICE],
        ),
        _point(
            "acme-deleted",
            [0.98, 0.2],
            classification=Classification.PUBLIC,
            deleted_at=datetime.now(UTC).isoformat(),
        ),
        _point(
            "acme-pending",
            [0.97, 0.25],
            classification=Classification.PUBLIC,
            status="pending",
        ),
        _point("acme-no-grant", [0.95, 0.3]),
        _point(
            "globex-public",
            [1.0, 0.0],
            tenant_id=_TENANT_GLOBEX,
            classification=Classification.PUBLIC,
        ),
    ]
    client.upsert(collection_name="chunks", points=points)
    names = {str(point.payload["title"]): UUID(str(point.id)) for point in points}
    return QdrantVectorStore(client, collection_name="chunks"), names


def test_qdrant_store_applies_acl_and_row_state_filters(
    seeded_store: tuple[QdrantVectorStore, dict[str, UUID]],
) -> None:
    store, _ids = seeded_store

    chunks = store.search_with_context(
        embedding=[1.0, 0.0],
        ctx=_context(groups={_GROUP_RESEARCH}),
        top_k=20,
    )

    assert [chunk.content for chunk in chunks] == [
        "acme-public",
        "acme-user",
        "acme-group",
        "acme-department",
    ]
    assert [chunk.score for chunk in chunks] == pytest.approx([1.0, 0.8, 0.6, 0.0])
    assert all(chunk.metadata == {"source": chunk.content} for chunk in chunks)


def test_qdrant_store_never_crosses_tenants(
    seeded_store: tuple[QdrantVectorStore, dict[str, UUID]],
) -> None:
    store, _ids = seeded_store

    chunks = store.search_with_context(
        embedding=[1.0, 0.0],
        ctx=_context(tenant_id=_TENANT_GLOBEX),
        top_k=20,
    )

    assert [chunk.content for chunk in chunks] == ["globex-public"]


def test_qdrant_store_excludes_classification_above_clearance(
    seeded_store: tuple[QdrantVectorStore, dict[str, UUID]],
) -> None:
    store, _ids = seeded_store

    chunks = store.search_with_context(
        embedding=[1.0, 0.0],
        ctx=_context(classification=Classification.PUBLIC),
        top_k=20,
    )

    assert [chunk.content for chunk in chunks] == ["acme-public"]


def test_protocol_search_directs_callers_to_context_adapter(
    seeded_store: tuple[QdrantVectorStore, dict[str, UUID]],
) -> None:
    store, _ids = seeded_store

    with pytest.raises(NotImplementedError, match="search_with_context"):
        store.search(embedding=[1.0, 0.0], policy_predicate=object(), top_k=1)
