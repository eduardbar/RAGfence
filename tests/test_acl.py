"""ACL predicate tests (task 4.5, no DB).

Spec reference: openspec/changes/ragfence-foundation/specs/storage-schema/spec.md
- Normalized ACL vs JSONB Metadata / Scenario: Metadata spoofing has no effect
- Repositories / Scenario: Tenant isolation (predicate side)

The predicate is compiled to PostgreSQL SQL (no database) and asserted to
reference typed ACL columns only — never the JSONB ``metadata`` — and to
reflect deny-by-default scoping (BACKEND_SCHEMA §9.1).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext
from ragfence.db.models import DocumentACL as DocumentACLModel
from ragfence.db.repositories import build_acl_predicate

TENANT_A = uuid4()
TENANT_B = uuid4()
ENGINEERING = uuid4()
FINANCE = uuid4()
USER = uuid4()


def _ctx(
    *,
    department_id: UUID | None,
    classification: Classification = Classification.INTERNAL,
    user_id: UUID = USER,
    groups: set[UUID] | None = None,
) -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=TENANT_A,
        user_id=user_id,
        department_id=department_id,
        classification=classification,
        allowed_user_ids={user_id},
        allowed_group_ids=groups or set(),
        is_authenticated=True,
        source="synthetic",
    )


def _compiled(
    ctx: AuthorizationContext, *, acl: Any = DocumentACLModel
) -> tuple[str, dict[str, Any]]:
    stmt = select(DocumentACLModel).where(build_acl_predicate(acl, ctx))
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def test_predicate_uses_typed_acl_columns_only() -> None:
    sql, _ = _compiled(_ctx(department_id=ENGINEERING, groups={uuid4()}))
    assert "document_acl.tenant_id" in sql
    assert "document_acl.classification" in sql
    assert "document_acl.department_id" in sql
    assert "allowed_user_ids" in sql
    assert "allowed_group_ids" in sql
    assert "ANY (document_acl.allowed_user_ids)" in sql
    assert "&&" in sql  # group allowlist overlap
    assert "document_acl.department_id IS NOT NULL" in sql


def test_predicate_never_references_jsonb_metadata() -> None:
    sql, _ = _compiled(_ctx(department_id=ENGINEERING, groups={uuid4()}))
    assert "metadata" not in sql


def test_predicate_denies_without_grants_and_without_department() -> None:
    """deny-by-default: no grant and no department match leaves no satisfiable branch."""
    ctx = _ctx(department_id=None)
    sql, params = _compiled(ctx)
    assert "IS NOT NULL" in sql  # department branch requires a real department
    assert params["allowed_group_ids_1"] == []  # empty grant list binds as empty array
    assert "department_id IS NULL" in sql  # None ctx department renders IS NULL (never true)


def test_predicate_grant_branches_are_the_only_alternatives() -> None:
    predicate = build_acl_predicate(DocumentACLModel, _ctx(department_id=None))
    and_clauses = predicate.clauses
    assert len(and_clauses) == 3  # tenant, classification rank, grant/department OR
    grant_branch = and_clauses[2]
    inner = getattr(grant_branch, "element", grant_branch)  # unwrap Grouping if present
    assert len(inner.clauses) == 4  # public access, user grant, group grant, department match

    public_access = inner.clauses[0]
    assert "classification" in str(public_access.left)
    assert public_access.right.effective_value == Classification.PUBLIC

    user_grant = inner.clauses[1]
    assert "allowed_user_ids" in str(user_grant.left)

    group_grant = inner.clauses[2]
    assert "allowed_group_ids" in str(group_grant.left)

    department_match = inner.clauses[3]
    assert len(department_match.clauses) == 2  # IS NOT NULL AND department_id = ctx


def test_predicate_rank_case_covers_all_classifications() -> None:
    sql, params = _compiled(_ctx(department_id=ENGINEERING))
    assert "case" in sql.lower()
    classification_values = ("public", "internal", "confidential", "restricted")
    classification_params = [value for value in params.values() if value in classification_values]
    assert set(classification_params) == {
        "public",
        "internal",
        "confidential",
        "restricted",
    }


def test_predicate_scopes_to_ctx_tenant_only() -> None:
    """A cross-tenant ctx yields a tenant predicate on its own tenant id."""
    ctx = _ctx(department_id=ENGINEERING)
    sql, params = _compiled(ctx)
    tenant_param = next(value for key, value in params.items() if key.startswith("tenant_id"))
    assert str(tenant_param) == str(TENANT_A)
    assert str(TENANT_B) not in [str(value) for value in params.values()]


def test_classification_escalation_is_denied() -> None:
    """A RESTRICTED document vs an INTERNAL ctx: rank 3 <= 1 is false (denied)."""
    ctx = _ctx(department_id=ENGINEERING, classification=Classification.INTERNAL)
    predicate = build_acl_predicate(DocumentACLModel, ctx)
    rank_comparison = predicate.clauses[1]
    assert "case" in str(rank_comparison.left).lower()
    assert rank_comparison.right.effective_value == Classification.INTERNAL.rank
