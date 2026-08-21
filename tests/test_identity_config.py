"""Identity strategy configuration tests (spec R4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ragfence.adapters.generic_http import GenericHTTPConfig


def test_headers_identity_accepts_allowed_placeholders() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "headers",
                "headers": {
                    "X-User-Id": "{actor_user_id}",
                    "X-Tenant-Id": "{actor_tenant_id}",
                },
            },
        }
    )
    assert config.identity is not None
    assert config.identity.kind == "headers"


def test_headers_identity_rejects_unknown_placeholder() -> None:
    with pytest.raises(ValidationError, match="unknown placeholder.*actor_email"):
        GenericHTTPConfig.model_validate(
            {
                "base_url": "https://rag.example.test",
                "retrieve_path": "retrieve",
                "identity": {
                    "kind": "headers",
                    "headers": {"X-Email": "{actor_email}"},
                },
            }
        )


def test_bearer_identity_requires_token_env() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
            "identity": {
                "kind": "bearer",
                "token_env": "RAGFENCE_BEARER_TOKEN",
            },
        }
    )
    assert config.identity is not None
    assert config.identity.kind == "bearer"
    assert config.identity.header_name == "Authorization"


def test_bearer_identity_rejects_empty_token_env() -> None:
    with pytest.raises(ValidationError, match="token_env"):
        GenericHTTPConfig.model_validate(
            {
                "base_url": "https://rag.example.test",
                "retrieve_path": "retrieve",
                "identity": {
                    "kind": "bearer",
                    "token_env": "",
                },
            }
        )


def test_identity_none_by_default() -> None:
    config = GenericHTTPConfig.model_validate(
        {
            "base_url": "https://rag.example.test",
            "retrieve_path": "retrieve",
        }
    )
    assert config.identity is None
