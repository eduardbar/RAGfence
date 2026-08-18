"""End-to-end adapter verification against deterministic local routes."""

from __future__ import annotations

from urllib.request import Request
from uuid import UUID

import pytest

from ragfence.adapters.errors import AdapterError, AdapterTransportError, UnsupportedOperationError
from ragfence.adapters.generic_http import (
    GenericHTTPAdapter,
    GenericHTTPConfig,
    GenericHTTPTransport,
    _HTTPResponse,
)
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, RetrievalRequest
from tests.support.generic_http_stub import GenericHTTPStub, json_response, text_response

REQUEST = RetrievalRequest(
    query="What is the approval policy?",
    top_k=2,
    authorization=AuthorizationContext(
        tenant_id=UUID("00000000-0000-0000-0000-000000000010"),
        user_id=UUID("00000000-0000-0000-0000-000000000011"),
        department_id=None,
        classification=Classification.INTERNAL,
        allowed_user_ids=set(),
        allowed_group_ids=set(),
        is_authenticated=True,
        source="synthetic",
    ),
)
CHUNK = {
    "chunk_id": "00000000-0000-0000-0000-000000000001",
    "document_id": "00000000-0000-0000-0000-000000000002",
    "document_title": "Policy",
    "chunk_index": 0,
    "content": "Approval is required.",
    "score": 0.9,
    "metadata": {"classification": Classification.INTERNAL.value},
}


def config(stub: GenericHTTPStub, **overrides: object) -> GenericHTTPConfig:
    values: dict[str, object] = {
        "base_url": stub.base_url,
        "retrieve_path": "retrieve",
        "answer_path": "chat",
        "health_path": "health",
        "timeout_seconds": 1.5,
        "auth_token": "integration-secret",
    }
    values.update(overrides)
    return GenericHTTPConfig.model_validate(values)


def test_stub_routes_cover_retrieve_chat_health_and_auth() -> None:
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    stub.route("POST", "/chat", json_response({"answer": "Approval is required."}))
    stub.route("GET", "/health", json_response({"status": "ok"}))
    adapter = GenericHTTPAdapter(
        config(stub), transport=GenericHTTPTransport(config(stub), opener=stub)
    )

    chunks = adapter.retrieve(REQUEST)
    answer = adapter.answer(REQUEST, chunks)

    assert chunks[0].content == CHUNK["content"]
    assert answer == "Approval is required."
    assert adapter.is_healthy() is True
    assert stub.requests[0][2] == {"question": REQUEST.query, "top_k": REQUEST.top_k}
    context_payload = stub.requests[1][2]
    assert isinstance(context_payload, dict)
    context = context_payload["context"]
    assert isinstance(context, list)
    assert isinstance(context[0], dict)
    assert context[0]["content"] == CHUNK["content"]
    assert stub.requests[0][3]["Authorization"] == "Bearer integration-secret"


def test_retrieval_only_does_not_call_chat() -> None:
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    adapter = GenericHTTPAdapter(
        config(stub, answer_path=None),
        transport=GenericHTTPTransport(config(stub, answer_path=None), opener=stub),
    )

    assert len(adapter.retrieve(REQUEST)) == 1
    with pytest.raises(UnsupportedOperationError, match="answer"):
        adapter.answer(REQUEST, [])
    assert [path for _, path, _, _ in stub.requests] == ["/retrieve"]


@pytest.mark.parametrize(
    "response",
    [
        text_response("not-json"),
        json_response(
            {"chunks": [{key: value for key, value in CHUNK.items() if key != "document_id"}]}
        ),
    ],
)
def test_retrieve_non_json_and_missing_fields_fail_closed(response: object) -> None:
    stub = GenericHTTPStub()
    if isinstance(response, type(text_response(""))):
        stub.route("POST", "/retrieve", response)
    else:
        stub.route("POST", "/retrieve", response)  # type: ignore[arg-type]
    adapter = GenericHTTPAdapter(
        config(stub), transport=GenericHTTPTransport(config(stub), opener=stub)
    )

    with pytest.raises(AdapterError):
        adapter.retrieve(REQUEST)


def test_retrieve_timeout_is_typed_and_not_retried() -> None:
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", TimeoutError("integration-secret timeout"))
    adapter = GenericHTTPAdapter(
        config(stub), transport=GenericHTTPTransport(config(stub), opener=stub)
    )

    with pytest.raises(AdapterError) as caught:
        adapter.retrieve(REQUEST)
    assert "integration-secret" not in str(caught.value)
    assert len(stub.requests) == 1


def test_health_retry_exhaustion_and_four_xx_no_retry() -> None:
    exhausted = GenericHTTPStub()
    exhausted.route("GET", "/health", *[json_response({"status": "down"}, 503) for _ in range(3)])
    sleeps: list[float] = []
    transport = GenericHTTPTransport(
        config(exhausted, health_retries=2, health_backoff_seconds=0.1),
        opener=exhausted,
        sleeper=sleeps.append,
    )
    assert transport.health() is False
    assert len(exhausted.requests) == 3
    assert sleeps == [0.1, 0.2]

    unauthorized = GenericHTTPStub()
    unauthorized.route("GET", "/health", json_response({"status": "denied"}, 401))
    sleeps.clear()
    assert (
        GenericHTTPTransport(
            config(unauthorized), opener=unauthorized, sleeper=sleeps.append
        ).health()
        is False
    )
    assert len(unauthorized.requests) == 1
    assert sleeps == []


def test_auth_redaction_and_malformed_health_json() -> None:
    stub = GenericHTTPStub()
    stub.route("POST", "/retrieve", text_response("integration-secret response", 401))
    stub.route("GET", "/health", text_response("not-json"))
    transport = GenericHTTPTransport(config(stub), opener=stub)

    with pytest.raises(AdapterTransportError) as caught:
        transport.post_json("retrieve", {})
    assert "integration-secret" not in str(caught.value)
    assert "response" not in str(caught.value)
    with pytest.raises(AdapterError, match="not JSON"):
        transport.get_json("health")


def test_timeout_argument_is_finite_for_every_stub_request() -> None:
    stub = GenericHTTPStub()
    stub.route("GET", "/health", json_response({"status": "ok"}))
    seen: list[float] = []

    def opener(request: Request, timeout: float) -> _HTTPResponse:
        seen.append(timeout)
        return stub(request, timeout)

    assert GenericHTTPTransport(config(stub, timeout_seconds=0.75), opener=opener).health() is True
    assert seen == [0.75]
