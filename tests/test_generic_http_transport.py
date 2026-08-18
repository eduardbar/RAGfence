"""TDD transport/auth contract tests for the generic HTTP adapter."""

from __future__ import annotations

import io
from urllib.request import Request

import pytest

from ragfence.adapters.errors import AdapterError, AdapterTransportError
from ragfence.adapters.generic_http import GenericHTTPConfig, GenericHTTPTransport


class StubResponse:
    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def __enter__(self) -> StubResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self._body.close()

    def read(self) -> bytes:
        return self._body.read()


class Recorder:
    def __init__(self, responses: list[object]) -> None:
        self.requests: list[Request] = []
        self.responses = responses

    def __call__(self, request: Request, timeout: float) -> StubResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def _config(**overrides: object) -> GenericHTTPConfig:
    values: dict[str, object] = {
        "base_url": "https://rag.example.test/api/",
        "retrieve_path": "retrieve",
        "answer_path": "answer",
        "health_path": "health",
        "timeout_seconds": 2.5,
        "auth_token": "top-secret",
    }
    values.update(overrides)
    return GenericHTTPConfig.model_validate(values)


def test_json_post_and_get_join_paths_and_send_bearer_without_secret_in_errors() -> None:
    recorder = Recorder([StubResponse(body=b'{"ok":true}'), StubResponse(body=b'{"ok":true}')])
    transport = GenericHTTPTransport(_config(), opener=recorder)

    transport.post_json("retrieve", {"question": "hello"})
    transport.get_json("health")

    assert recorder.requests[0].full_url == "https://rag.example.test/api/retrieve"
    assert recorder.requests[0].method == "POST"
    assert recorder.requests[0].get_header("Authorization") == "Bearer top-secret"
    assert recorder.requests[0].data == b'{"question":"hello"}'
    assert recorder.requests[1].full_url == "https://rag.example.test/api/health"
    assert recorder.requests[1].method == "GET"
    assert recorder.requests[1].data is None


def test_every_request_uses_configured_finite_timeout() -> None:
    timeouts: list[float] = []

    def opener(request: Request, timeout: float) -> StubResponse:
        timeouts.append(timeout)
        return StubResponse()

    transport = GenericHTTPTransport(_config(timeout_seconds=1.25), opener=opener)
    transport.post_json("retrieve", {})
    transport.get_json("health")

    assert timeouts == [1.25, 1.25]


def test_non_success_status_raises_typed_error_without_response_body_or_token() -> None:
    recorder = Recorder([StubResponse(status=401, body=b"secret response")])
    transport = GenericHTTPTransport(_config(), opener=recorder)

    with pytest.raises(AdapterTransportError) as caught:
        transport.post_json("retrieve", {})

    assert caught.value.status_code == 401
    assert "top-secret" not in str(caught.value)
    assert "secret response" not in str(caught.value)


def test_transport_failure_is_typed_and_secret_safe() -> None:
    recorder = Recorder([TimeoutError("Bearer top-secret connection details")])
    transport = GenericHTTPTransport(_config(), opener=recorder)

    with pytest.raises(AdapterError) as caught:
        transport.post_json("retrieve", {})

    assert "top-secret" not in str(caught.value)
    assert "connection details" not in str(caught.value)


def test_health_retries_connection_timeout_and_5xx_with_bounded_exponential_backoff() -> None:
    sleeps: list[float] = []
    recorder = Recorder(
        [
            TimeoutError(),
            StubResponse(status=503),
            StubResponse(status=502),
            StubResponse(status=200, body=b"ok"),
        ]
    )
    transport = GenericHTTPTransport(
        _config(health_retries=4, health_backoff_seconds=2.0),
        opener=recorder,
        sleeper=sleeps.append,
    )

    assert transport.health() is True
    assert len(recorder.requests) == 4
    assert sleeps == [2.0, 4.0, 8.0]


def test_health_does_not_retry_4xx() -> None:
    sleeps: list[float] = []
    recorder = Recorder([StubResponse(status=401)])
    transport = GenericHTTPTransport(
        _config(health_retries=4), opener=recorder, sleeper=sleeps.append
    )

    assert transport.health() is False
    assert len(recorder.requests) == 1
    assert sleeps == []


def test_health_exhaustion_returns_false_and_caps_backoff() -> None:
    sleeps: list[float] = []
    recorder = Recorder([StubResponse(status=503) for _ in range(11)])
    transport = GenericHTTPTransport(
        _config(health_retries=10, health_backoff_seconds=60.0),
        opener=recorder,
        sleeper=sleeps.append,
    )

    assert transport.health() is False
    assert len(recorder.requests) == 11
    assert max(sleeps) <= 60.0


def test_post_operations_never_retry_transient_failures() -> None:
    recorder = Recorder([StubResponse(status=503), StubResponse(status=200)])
    transport = GenericHTTPTransport(_config(), opener=recorder)

    with pytest.raises(AdapterTransportError):
        transport.post_json("answer", {})

    assert len(recorder.requests) == 1


def test_configured_header_name_is_used_for_bearer() -> None:
    recorder = Recorder([StubResponse()])
    transport = GenericHTTPTransport(_config(auth_header="X-Static-Auth"), opener=recorder)

    transport.get_json("health")

    assert recorder.requests[0].get_header("X-static-auth") == "Bearer top-secret"
    assert recorder.requests[0].get_header("Authorization") is None


def test_transport_rejects_absolute_or_query_endpoint_paths() -> None:
    transport = GenericHTTPTransport(_config(), opener=Recorder([]))

    with pytest.raises(ValueError, match="relative paths"):
        transport.get_json("https://evil.example/steal")

    with pytest.raises(ValueError, match="relative paths"):
        transport.get_json("health?token=secret")
