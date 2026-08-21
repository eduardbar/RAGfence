"""Loader row-plan unit tests (PR 2, task 2.1).

Spec reference: openspec/changes/ragfence-acme-dataset/specs/synthetic-dataset/spec.md
- DB Loader Path / Scenario: Seeds schema cleanly (FK-ordered rows, natural
  unique keys, lowercase enum values)
- Synthetic Document Corpus: board-plan is department-less (NULL department on
  both the document and ACL rows; grant solely via the ``executives`` allowlist)

The row plan is a pure mapping (design: loader decision): no session, no I/O,
so these tests run without a database. Enum columns carry the enum MEMBER; the
ORM ``values_callable`` persists the member's lowercase ``.value``.
"""

from ragfence.core.enums import Classification, DocumentStatus
from ragfence.datasets import SEED, build_acme_corp, build_globex_corp
from ragfence.datasets.loader import RowPlan, _build_row_plan

EXPECTED_KIND_ORDER = (
    "tenant",
    "department",
    "group",
    "user",
    "user_group",
    "document",
    "document_acl",
    "document_chunk",
)

BOARD_PLAN_PATH = "executive/strategy/2026-board-plan.pdf"


def _plans() -> tuple[RowPlan, ...]:
    return _build_row_plan(build_acme_corp(SEED))


def _count(plans: tuple[RowPlan, ...], kind: str) -> int:
    return sum(1 for plan in plans if plan.kind == kind)


def test_plan_entities_follow_fk_dependency_order() -> None:
    """S8: tenant -> departments -> groups -> users -> user_groups -> documents
    -> document_acl -> document_chunks; each kind is contiguous."""
    plans = _plans()
    kinds = [plan.kind for plan in plans]
    first_seen = [
        kind for index, kind in enumerate(kinds) if index == 0 or kind != kinds[index - 1]
    ]
    assert first_seen == list(EXPECTED_KIND_ORDER)
    # Contiguity: every row of an earlier kind precedes every row of a later kind.
    assert kinds == sorted(kinds, key=EXPECTED_KIND_ORDER.index)
    assert len(plans) == 33  # 1 + 5 + 2 + 7 + 3 + 5 + 5 + 5


def test_plan_shapes_and_counts_match_corpus() -> None:
    plans = _plans()
    assert _count(plans, "tenant") == 1
    assert _count(plans, "department") == 5
    assert _count(plans, "group") == 2
    assert _count(plans, "user") == 7
    assert _count(plans, "user_group") == 3
    assert _count(plans, "document") == 5
    assert _count(plans, "document_acl") == 5
    assert _count(plans, "document_chunk") == 5


def test_plan_carries_natural_unique_keys() -> None:
    """Each plan names the get-or-create lookup columns (S8: natural keys)."""
    ds = build_acme_corp(SEED)
    plans = _plans()
    by_kind = {kind: [p for p in plans if p.kind == kind] for kind in EXPECTED_KIND_ORDER}

    assert dict(by_kind["tenant"][0].key) == {"slug": ds.tenant.slug}
    assert {dict(p.key)["slug"] for p in by_kind["department"]} == set(ds.departments)
    assert {dict(p.key)["slug"] for p in by_kind["group"]} == set(ds.groups)
    assert {dict(p.key)["email"] for p in by_kind["user"]} == set(ds.users)
    assert {dict(p.key)["user_id"] for p in by_kind["user_group"]} == {
        user_id for user_id, _ in ds.user_groups
    }
    assert {dict(p.key)["checksum"] for p in by_kind["document"]} == {
        doc.checksum for doc in ds.documents.values()
    }
    assert {dict(p.key)["document_id"] for p in by_kind["document_acl"]} == {
        doc.id for doc in ds.documents.values()
    }
    assert {dict(p.key)["document_id"] for p in by_kind["document_chunk"]} == {
        doc.id for doc in ds.documents.values()
    }


def test_plan_enum_values_are_lowercase_members() -> None:
    """Loader passes enum MEMBERS; values_callable persists lowercase (S8)."""
    plans = _plans()
    statuses = {plan.values["status"] for plan in plans if plan.kind == "document"}
    classifications = {
        plan.values["classification"] for plan in plans if plan.kind in ("document", "document_acl")
    }
    assert statuses == {DocumentStatus.READY}
    assert {status.value for status in statuses} == {"ready"}
    assert classifications == {
        Classification.PUBLIC,
        Classification.INTERNAL,
        Classification.CONFIDENTIAL,
        Classification.RESTRICTED,
    }
    assert {cls.value for cls in classifications} == {
        "public",
        "internal",
        "confidential",
        "restricted",
    }
    assert all(cls.value == cls.value.lower() for cls in classifications)


def test_board_plan_department_is_null_on_document_and_acl() -> None:
    """S8/board-plan: NULL department on BOTH rows; sole grant via executives."""
    ds = build_acme_corp(SEED)
    board = ds.documents[BOARD_PLAN_PATH]
    plans = _plans()
    document_plan = next(
        plan for plan in plans if plan.kind == "document" and plan.values["id"] == board.id
    )
    acl_plan = next(
        plan
        for plan in plans
        if plan.kind == "document_acl" and plan.values["document_id"] == board.id
    )
    assert document_plan.values["department_id"] is None
    assert acl_plan.values["department_id"] is None
    assert acl_plan.values["allowed_group_ids"] == [ds.groups["executives"].id]
    assert acl_plan.values["allowed_user_ids"] == []
    # Contrast: every other document keeps its department scope on both rows.
    non_board_documents = [
        plan for plan in plans if plan.kind == "document" and plan.values["id"] != board.id
    ]
    non_board_acls = [
        plan
        for plan in plans
        if plan.kind == "document_acl" and plan.values["document_id"] != board.id
    ]
    assert len(non_board_documents) == 4
    assert len(non_board_acls) == 4
    assert all(plan.values["department_id"] is not None for plan in non_board_documents)
    assert all(plan.values["department_id"] is not None for plan in non_board_acls)


def test_every_document_has_one_chunk_with_null_embedding() -> None:
    """Design: one chunk per document (chunk_index=0, embedding=None)."""
    plans = _plans()
    chunk_plans = [plan for plan in plans if plan.kind == "document_chunk"]
    assert len(chunk_plans) == 5
    assert {plan.values["chunk_index"] for plan in chunk_plans} == {0}
    assert all(plan.values["embedding"] is None for plan in chunk_plans)
    assert all(plan.values["content"] for plan in chunk_plans)


def test_document_plan_carries_required_not_null_columns() -> None:
    """Documents need title/source/checksum; users need a password hash."""
    plans = _plans()
    for plan in plans:
        if plan.kind == "document":
            assert plan.values["title"]
            assert plan.values["source"] == "acme-synthetic"
            assert plan.values["checksum"]
        if plan.kind == "user":
            assert plan.values["password_hash"]
            assert plan.values["display_name"]


def test_globex_plan_uses_its_own_tenant_and_user_natural_keys() -> None:
    globex = build_globex_corp(SEED)
    plans = _build_row_plan(globex)

    assert dict(plans[0].key) == {"slug": "globex-corp"}
    user_emails = {dict(plan.key)["email"] for plan in plans if plan.kind == "user"}
    assert "engineering_employee@globex-corp.example" in user_emails
