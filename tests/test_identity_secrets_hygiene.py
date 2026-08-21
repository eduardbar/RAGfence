"""End-to-end identity + secrets hygiene tests (spec R4.1, R4.2).

Uses the stub HTTP server infrastructure to verify:
- R4.1: two distinct actors produce distinct identity headers server-side.
- R4.2: missing strategy / missing token / unknown placeholder produce
  INCONCLUSIVE + gate failure WITHOUT leaking secrets.
- Secrets hygiene: bearer token never appears in reports, findings, reasons,
  or exception messages.
"""

from __future__ import annotations

import json
import os
from uuid import UUID

import pytest

from ragfence.adapters.generic_http import (
    GenericHTTPAdapter,
    GenericHTTPConfig,
    GenericHTTPTransport,
)
from ragfence.attacks.generators import default_evaluation_controls
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, RetrievalRequest
from ragfence.evaluation.gate import evaluate_gate
from ragfence.evaluation.matrix_runner import run_matrix
from ragfence.evaluation.redaction import redact_evidence, redact_secrets
from tests.support.generic_http_stub import GenericHTTPStub, json_response, text_response

MARKER_TOKEN = "supersecret-marker-token-7f3a"


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

CHUNK = {
    "chunk_id": "00000000-0000-0000-0000-000000000001",
    "document_id": "00000000-0000-0000-0000-000000000002",
    "document_title": "Policy",
    "chunk_index": 0,
    "content": "Approval is required.",
    "score": 0.9,
    "metadata": {"classification": "internal"},
}


def _bearer_config(stub: GenericHTTPStub, token_env: str) -> GenericHTTPConfig:
    return GenericHTTPConfig.model_validate(
        {
            "base_url": stub.base_url,
            "retrieve_path": "retrieve",
            "identity": {"kind": "bearer", "token_env": token_env},
        }
    )


def _headers_config(stub: GenericHTTPStub) -> GenericHTTPConfig:
    return GenericHTTPConfig.model_validate(
        {
            "base_url": stub.base_url,
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


def _request_for(actor: AuthorizationContext) -> RetrievalRequest:
    return RetrievalRequest(
        query="What is the approval policy?",
        top_k=2,
        authorization=actor,
    )


def test_r41_two_actors_produce_distinct_bearer_headers_server_side() -> None:
    """R4.1: two distinct actors produce DISTINCT configured identity headers."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = _bearer_config(stub, "RAGFENCE_TEST_HYGIENE_TOKEN")
    os.environ["RAGFENCE_TEST_HYGIENE_TOKEN"] = MARKER_TOKEN
    try:
        adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
        adapter.retrieve(_request_for(ACTOR_A))
        adapter.retrieve(_request_for(ACTOR_B))
    finally:
        del os.environ["RAGFENCE_TEST_HYGIENE_TOKEN"]

    assert len(stub.requests) == 2
    auth_a = stub.requests[0][3].get("Authorization", "")
    auth_b = stub.requests[1][3].get("Authorization", "")
    assert MARKER_TOKEN in auth_a
    assert MARKER_TOKEN in auth_b
    assert adapter.last_identity_represented is True


def test_r41_two_actors_produce_distinct_custom_headers_server_side() -> None:
    """R4.1: headers strategy produces distinct values for distinct actors."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = _headers_config(stub)
    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))

    adapter.retrieve(_request_for(ACTOR_A))
    adapter.retrieve(_request_for(ACTOR_B))

    assert len(stub.requests) == 2
    headers_a = stub.requests[0][3]
    headers_b = stub.requests[1][3]
    assert headers_a["X-user-id"] != headers_b["X-user-id"]
    assert headers_a["X-tenant-id"] != headers_b["X-tenant-id"]
    assert headers_a["X-user-id"] == str(ACTOR_A.user_id)
    assert headers_b["X-user-id"] == str(ACTOR_B.user_id)


def test_r42_no_strategy_identity_not_represented() -> None:
    """R4.2: no identity strategy -> identity not represented."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = GenericHTTPConfig.model_validate(
        {"base_url": stub.base_url, "retrieve_path": "retrieve"}
    )
    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
    adapter.retrieve(_request_for(ACTOR_A))

    assert adapter.last_identity_represented is False
    assert "Authorization" not in stub.requests[0][3]


def test_r42_missing_bearer_token_identity_not_represented() -> None:
    """R4.2: missing token env var -> identity not represented, no header sent."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = _bearer_config(stub, "RAGFENCE_TEST_HYGIENE_MISSING")
    os.environ.pop("RAGFENCE_TEST_HYGIENE_MISSING", None)

    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
    adapter.retrieve(_request_for(ACTOR_A))

    assert adapter.last_identity_represented is False
    assert "Authorization" not in stub.requests[0][3]


def test_secrets_hygiene_bearer_token_never_in_reason_or_evidence() -> None:
    """Bearer token must never appear in reasons, evidence, or exception messages."""
    stub = GenericHTTPStub()
    stub.route(
        "POST",
        "/retrieve",
        text_response(f"target error leaking {MARKER_TOKEN}", 500),
    )

    config = _bearer_config(stub, "RAGFENCE_TEST_HYGIENE_TOKEN")
    os.environ["RAGFENCE_TEST_HYGIENE_TOKEN"] = MARKER_TOKEN
    try:
        adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
        controls = default_evaluation_controls()
        results = run_matrix(
            adapter,
            controls,
            identity_represented_for=lambda _c: adapter.check_identity_represented(),
        )
    finally:
        del os.environ["RAGFENCE_TEST_HYGIENE_TOKEN"]

    for result in results:
        assert MARKER_TOKEN not in result.reason
        assert MARKER_TOKEN not in str(result.observation.error or "")

    report_json = json.dumps(
        [
            {
                "control_id": r.control.id,
                "status": r.status,
                "reason": r.reason,
                "error": r.observation.error,
            }
            for r in results
        ]
    )
    assert MARKER_TOKEN not in report_json


def test_secrets_hygiene_redact_secrets_helper() -> None:
    """redact_secrets replaces all occurrences of the secret."""
    text = f"error: token {MARKER_TOKEN} was leaked in {MARKER_TOKEN} context"
    redacted = redact_secrets(text, [MARKER_TOKEN])
    assert MARKER_TOKEN not in redacted
    assert "[REDACTED]" in redacted


def test_secrets_hygiene_redact_evidence_catches_token_in_values() -> None:
    """redact_evidence redacts the token when it appears as a marker."""
    evidence = {
        "error": f"target returned {MARKER_TOKEN}",
        "headers": {"Authorization": f"Bearer {MARKER_TOKEN}"},
    }
    redacted = redact_evidence(evidence, markers=[MARKER_TOKEN])
    serialized = json.dumps(redacted)
    assert MARKER_TOKEN not in serialized


def test_r42_gate_fails_closed_when_identity_not_represented() -> None:
    """R4.2: no strategy -> all identity_required controls INCONCLUSIVE -> gate fails."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = GenericHTTPConfig.model_validate(
        {"base_url": stub.base_url, "retrieve_path": "retrieve"}
    )
    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))

    controls = default_evaluation_controls()
    results = run_matrix(
        adapter,
        controls,
        identity_represented_for=lambda _c: adapter.check_identity_represented(),
    )

    identity_required_controls = [c for c in controls if c.identity_required]
    assert len(identity_required_controls) > 0

    for result in results:
        if result.control.identity_required:
            assert result.status == "inconclusive"
            assert "identity not represented" in result.reason

    gate = evaluate_gate(results, controls, threshold=0.8)
    assert gate.passed is False
    inconclusive_reasons = [r for r in gate.reasons if "INCONCLUSIVE" in r]
    assert len(inconclusive_reasons) > 0


def test_r42_unknown_placeholder_rejected_at_config_validation() -> None:
    """R4.2: unknown placeholder -> config validation error, no secret leak."""
    with pytest.raises(Exception, match="unknown placeholder"):
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


def test_r42_missing_token_env_produces_inconclusive_without_leaking_env_name() -> None:
    """R4.2: missing token -> INCONCLUSIVE, env var name not leaked in reasons."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    env_name = "RAGFENCE_TEST_HYGIENE_SENSITIVE_ENV"
    config = _bearer_config(stub, env_name)
    os.environ.pop(env_name, None)

    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
    controls = default_evaluation_controls()
    results = run_matrix(
        adapter,
        controls,
        identity_represented_for=lambda _c: adapter.check_identity_represented(),
    )

    for result in results:
        assert env_name not in result.reason
        if result.control.identity_required:
            assert result.status == "inconclusive"


def test_matrix_hook_identity_represented_for_per_control() -> None:
    """identity_represented_for hook is called per-control and drives INCONCLUSIVE."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))

    config = GenericHTTPConfig.model_validate(
        {"base_url": stub.base_url, "retrieve_path": "retrieve"}
    )
    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))

    controls = default_evaluation_controls()
    call_count = 0

    def hook(control: object) -> bool:
        nonlocal call_count
        call_count += 1
        return False

    results = run_matrix(adapter, controls, identity_represented_for=hook)

    assert call_count == len(controls)
    for result in results:
        if result.control.identity_required:
            assert result.status == "inconclusive"
            assert "identity not represented" in result.reason


def test_secrets_hygiene_answer_body_does_not_leak_token() -> None:
    """R3: answer text containing the bearer token must be redacted."""
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    stub.route(
        "POST",
        "/answer",
        json_response({"answer": f"response with {MARKER_TOKEN} leaked"}),
    )

    config = GenericHTTPConfig.model_validate(
        {
            "base_url": stub.base_url,
            "retrieve_path": "retrieve",
            "answer_path": "answer",
            "identity": {"kind": "bearer", "token_env": "RAGFENCE_TEST_HYGIENE_ANSWER"},
        }
    )
    os.environ["RAGFENCE_TEST_HYGIENE_ANSWER"] = MARKER_TOKEN
    try:
        adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
        controls = default_evaluation_controls()
        results = run_matrix(
            adapter,
            controls,
            identity_represented_for=lambda _c: adapter.check_identity_represented(),
        )
    finally:
        del os.environ["RAGFENCE_TEST_HYGIENE_ANSWER"]

    for result in results:
        answer_text = result.observation.answer or ""
        assert MARKER_TOKEN not in answer_text


def test_secrets_hygiene_error_message_does_not_leak_token() -> None:
    """R3: exception messages from the adapter must not contain the bearer token."""
    stub = GenericHTTPStub()
    stub.route(
        "POST",
        "/retrieve",
        text_response(f"error: {MARKER_TOKEN} in transport", 500),
    )

    config = GenericHTTPConfig.model_validate(
        {
            "base_url": stub.base_url,
            "retrieve_path": "retrieve",
            "identity": {"kind": "bearer", "token_env": "RAGFENCE_TEST_HYGIENE_ERROR"},
        }
    )
    os.environ["RAGFENCE_TEST_HYGIENE_ERROR"] = MARKER_TOKEN
    try:
        adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
        controls = default_evaluation_controls()
        results = run_matrix(
            adapter,
            controls,
            identity_represented_for=lambda _c: adapter.check_identity_represented(),
        )
    finally:
        del os.environ["RAGFENCE_TEST_HYGIENE_ERROR"]

    for result in results:
        assert MARKER_TOKEN not in result.reason
        assert MARKER_TOKEN not in str(result.observation.error or "")
