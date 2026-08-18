from __future__ import annotations

import io
from urllib.request import Request

import pytest

from ragfence.providers.errors import (
    LLMHTTPError,
    LLMRateLimitError,
    LLMResponseTooLargeError,
    LLMTimeoutError,
)
from ragfence.providers.transport import LLMHTTPTransport


class StubResponse:
    def __init__(
        self,
        status: int = 200,
        body: bytes = b'{"ok": true}',
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._body = io.BytesIO(body)

    def __enter__(self) -> StubResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self._body.close()

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)


class Recorder:
    def __init__(self, responses: list[object]) -> None:
        self.requests: list[Request] = []
        self.responses = responses
        self.timeouts: list[float] = []

    def __call__(self, request: Request, timeout: float) -> StubResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def test_post_json_sends_compact_json_and_caller_headers() -> None:
    recorder = Recorder([StubResponse()])
    transport = LLMHTTPTransport("https://llm.test/v1/chat", timeout_seconds=2.5, opener=recorder)

    assert transport.post_json(
        {"model": "m", "messages": [{"content": "hi"}]}, {"x-api-key": "secret"}
    ) == {"ok": True}

    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.data == b'{"model":"m","messages":[{"content":"hi"}]}'
    assert request.get_header("Content-type") == "application/json"
    assert request.get_header("X-api-key") == "secret"
    assert recorder.timeouts == [2.5]


def test_response_body_is_bounded() -> None:
    recorder = Recorder([StubResponse(body=b'{"toolong": true}')])
    transport = LLMHTTPTransport("https://llm.test", max_response_bytes=8, opener=recorder)

    with pytest.raises(LLMResponseTooLargeError):
        transport.post_json({}, {})


def test_429_retries_with_safe_retry_after_and_exponential_backoff() -> None:
    sleeps: list[float] = []
    recorder = Recorder(
        [
            StubResponse(status=429, headers={"Retry-After": "2"}),
            StubResponse(status=429, headers={"Retry-After": "not-a-delay"}),
            StubResponse(),
        ]
    )
    transport = LLMHTTPTransport(
        "https://llm.test",
        max_attempts=3,
        backoff_seconds=1.0,
        max_backoff_seconds=5.0,
        opener=recorder,
        sleeper=sleeps.append,
    )

    assert transport.post_json({}, {}) == {"ok": True}
    assert sleeps == [2.0, 2.0]
    assert len(recorder.requests) == 3


def test_429_exhaustion_raises_typed_rate_limit_error() -> None:
    recorder = Recorder(
        [StubResponse(status=429, headers={"Retry-After": "999999"}) for _ in range(3)]
    )
    transport = LLMHTTPTransport(
        "https://llm.test", max_attempts=3, max_retry_after_seconds=7.0, opener=recorder
    )

    with pytest.raises(LLMRateLimitError) as caught:
        transport.post_json({}, {})

    assert caught.value.status_code == 429
    assert len(recorder.requests) == 3
    assert "999999" not in str(caught.value)


def test_client_4xx_is_not_retried() -> None:
    recorder = Recorder([StubResponse(status=401, body=b"api-key=secret")])
    transport = LLMHTTPTransport("https://llm.test", max_attempts=4, opener=recorder)

    with pytest.raises(LLMHTTPError) as caught:
        transport.post_json({}, {"Authorization": "Bearer secret"})

    assert caught.value.status_code == 401
    assert len(recorder.requests) == 1
    assert "secret" not in str(caught.value)


def test_timeout_is_retried_and_exhaustion_is_typed_and_secret_safe() -> None:
    sleeps: list[float] = []
    recorder = Recorder([TimeoutError("secret") for _ in range(3)])
    transport = LLMHTTPTransport(
        "https://llm.test", max_attempts=3, opener=recorder, sleeper=sleeps.append
    )

    with pytest.raises(LLMTimeoutError) as caught:
        transport.post_json({}, {"Authorization": "secret"})

    assert len(recorder.requests) == 3
    assert sleeps == [0.5, 1.0]
    assert "secret" not in str(caught.value)


def test_5xx_is_retried_and_exhaustion_is_typed() -> None:
    sleeps: list[float] = []
    recorder = Recorder(
        [StubResponse(status=503), StubResponse(status=502), StubResponse(status=500)]
    )
    transport = LLMHTTPTransport(
        "https://llm.test", max_attempts=3, opener=recorder, sleeper=sleeps.append
    )

    with pytest.raises(LLMHTTPError) as caught:
        transport.post_json({}, {})

    assert caught.value.status_code == 500
    assert len(recorder.requests) == 3
    assert sleeps == [0.5, 1.0]
