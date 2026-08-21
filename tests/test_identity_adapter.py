"""Adapter identity resolution tests (spec R4.1, R4.2)."""

from __future__ import annotations

import os
from uuid import UUID

from ragfence.adapters.generic_http import (
    GenericHTTPConfig,
    resolve_identity_headers,
)
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext


def _auth(user_id: str, tenant_id: str, department_id: str | None = None) -> AuthorizationContext:
    return AuthorizationContext(
        tenant_id=UUID(tenant_id),
        user_id=UUID(user_id),
        department_id=UUID(department_id) if department_id else None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    )


ACTOR_A = _auth(
    "00000000-0000-0000-0000-000000000011",
    "00000000-0000-0000-0000-000000000010",
    "00000000-0000-0000-0000-000000000012",
)
ACTOR_B = _auth(
    "00000000-0000-0000-0000-000000000021",
    "00000000-0000-0000-0000-000000000020",
)


def test_no_identity_strategy_returns_not_represented() -> None:
    headers, represented = resolve_identity_headers(None, ACTOR_A)
    assert headers == {}
    assert represented is False


def test_headers_identity_two_actors_produce_distinct_values() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "headers",
                "headers": {
                    "X-User-Id": "{actor_user_id}",
                    "X-Tenant-Id": "{actor_tenant_id}",
                    "X-Dept": "{actor_department_id}",
                },
            },
        }
    )
    headers_a, rep_a = resolve_identity_headers(config.identity, ACTOR_A)
    headers_b, rep_b = resolve_identity_headers(config.identity, ACTOR_B)

    assert rep_a is True
    assert rep_b is True
    assert headers_a["X-User-Id"] != headers_b["X-User-Id"]
    assert headers_a["X-Tenant-Id"] != headers_b["X-Tenant-Id"]
    assert headers_a["X-Dept"] == str(ACTOR_A.department_id)
    assert headers_b["X-Dept"] == ""


def test_bearer_identity_resolves_token_from_env() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "bearer",
                "token_env": "RAGFENCE_TEST_BEARER_TOKEN",
            },
        }
    )
    os.environ["RAGFENCE_TEST_BEARER_TOKEN"] = "supersecret-marker-token"
    try:
        headers, represented = resolve_identity_headers(config.identity, ACTOR_A)
        assert represented is True
        assert headers == {"Authorization": "Bearer supersecret-marker-token"}
    finally:
        del os.environ["RAGFENCE_TEST_BEARER_TOKEN"]


def test_bearer_identity_missing_token_returns_not_represented() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "bearer",
                "token_env": "RAGFENCE_TEST_BEARER_TOKEN_MISSING",
            },
        }
    )
    os.environ.pop("RAGFENCE_TEST_BEARER_TOKEN_MISSING", None)
    headers, represented = resolve_identity_headers(config.identity, ACTOR_A)
    assert headers == {}
    assert represented is False


def test_bearer_identity_custom_header_name() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "bearer",
                "header_name": "X-Api-Token",
                "token_env": "RAGFENCE_TEST_CUSTOM_BEARER",
            },
        }
    )
    os.environ["RAGFENCE_TEST_CUSTOM_BEARER"] = "tok-123"
    try:
        headers, represented = resolve_identity_headers(config.identity, ACTOR_A)
        assert represented is True
        assert headers == {"X-Api-Token": "Bearer tok-123"}
    finally:
        del os.environ["RAGFENCE_TEST_CUSTOM_BEARER"]
