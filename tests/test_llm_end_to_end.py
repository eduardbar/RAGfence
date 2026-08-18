"""Offline Work Unit F verification through urllib opener seams."""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from typing import Any
from urllib.request import Request

import pytest

from ragfence.core.models import Message
from ragfence.evaluation.engine import EvaluationEngine
from ragfence.providers.llm import (
    AnthropicProvider,
    LLMConfig,
    LLMHTTPTransport,
    OllamaProvider,
    OpenAIProvider,
    ProviderParseError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTransportError,
    create_llm_provider,
)


class StubResponse:
    def __init__(
        self,
        status: int,
        body: object,
        headers: Mapping[str, str] | None = None,
        *,
        delay: float = 0.0,
    ) -> None:
        self.status = status
        self.headers = dict(headers or {})
        self.delay = delay
        self._body = io.BytesIO(json.dumps(body).encode())

    def __enter__(self) -> StubResponse:
        return self

    def __exit__(self, *args: object) -> None:
        self._body.close()

    def read(self) -> bytes:
        return self._body.read()


class LocalOpener:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.requests: list[Request] = []
        self.timeouts: list[float] = []

    def __call__(self, request: Request, timeout: float) -> StubResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        if not isinstance(result, StubResponse):
            raise TypeError("stub response must be a response or exception")
        if result.delay > timeout:
            raise TimeoutError("stub delay exceeded timeout")
        return result


def _messages() -> list[Message]:
    return [Message(role="system", content="Answer safely"), Message(role="user", content="hello")]


def _transport(opener: LocalOpener, *, attempts: int = 1, sleeper: Any = None) -> LLMHTTPTransport:
    return LLMHTTPTransport(
        "http://local.test",
        timeout=1.25,
        opener=opener,
        max_attempts=attempts,
        backoff=0.25,
        sleeper=sleeper or (lambda delay: None),
    )


def _selected_provider(config: LLMConfig, opener: LocalOpener, **kwargs: Any) -> Any:
    selection = create_llm_provider(
        config,
        environ={"OPENAI_API_KEY": "offline-openai", "ANTHROPIC_API_KEY": "offline-anthropic"},
    )
    selection.provider.transport = _transport(opener, **kwargs)
    return selection


def test_selection_to_openai_completion_returns_llm_response_and_redacts_key() -> None:
    opener = LocalOpener(
        [
            StubResponse(
                200,
                {
                    "choices": [{"message": {"content": "safe answer"}}],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 3},
                },
            )
        ]
    )
    selection = _selected_provider(
        LLMConfig(provider="openai", openai_base_url="http://local.test"), opener
    )

    response = selection.provider.complete(messages=_messages(), temperature=0.0)

    assert isinstance(response.content, str)
    assert response.prompt_tokens == 11
    assert response.completion_tokens == 3
    assert selection.metadata["provider"] == "openai"
    assert "offline-openai" not in repr(selection)
    assert opener.requests[0].full_url == "http://local.test/v1/chat/completions"
    assert opener.requests[0].get_header("Authorization") == "Bearer offline-openai"


def test_selection_to_anthropic_completion_maps_system_and_estimates_missing_usage() -> None:
    opener = LocalOpener([StubResponse(200, {"content": [{"type": "text", "text": "hello"}]})])
    selection = _selected_provider(
        LLMConfig(provider="anthropic", anthropic_base_url="http://local.test"), opener
    )

    response = selection.provider.complete(messages=_messages(), temperature=0.2)
    payload = json.loads(opener.requests[0].data or b"{}")

    assert response.content == "hello"
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0
    assert payload["system"] == "Answer safely"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert opener.requests[0].get_header("X-api-key") == "offline-anthropic"


def test_selection_to_ollama_completion_is_non_streaming_without_credentials() -> None:
    opener = LocalOpener([StubResponse(200, {"message": {"content": "local answer"}})])
    selection = create_llm_provider(
        LLMConfig(provider="ollama", ollama_base_url="http://local.test")
    )
    selection.provider.transport = _transport(opener)

    response = selection.provider.complete(messages=_messages(), temperature=0.0)
    payload = json.loads(opener.requests[0].data or b"{}")

    assert isinstance(selection.provider, OllamaProvider)
    assert response.content == "local answer"
    assert payload["stream"] is False
    assert opener.requests[0].full_url == "http://local.test/api/chat"
    assert not opener.requests[0].headers.get("Authorization")


@pytest.mark.parametrize(
    ("provider", "body"),
    [
        (OpenAIProvider, {"choices": []}),
        (AnthropicProvider, {"content": [{"type": "tool_use"}]}),
        (OllamaProvider, {"message": {"content": 42}}),
    ],
)
def test_malformed_provider_schema_fails_without_fabricated_answer(
    provider: type[Any], body: object
) -> None:
    opener = LocalOpener([StubResponse(200, body)])
    kwargs: dict[str, Any] = {"transport": _transport(opener)}
    if provider is not OllamaProvider:
        kwargs["api_key"] = "offline-secret"
    with pytest.raises(ProviderParseError):
        provider(**kwargs).complete(messages=_messages(), temperature=0.0)


def test_malformed_json_is_typed_and_explicit_provider_failure_is_not_fake() -> None:
    class BadJSON(StubResponse):
        def __init__(self) -> None:
            self.status = 200
            self.headers: dict[str, str] = {}
            self.delay = 0.0
            self._body = io.BytesIO(b"not-json")

    opener = LocalOpener([BadJSON()])
    selection = _selected_provider(LLMConfig(provider="openai"), opener)
    with pytest.raises(ProviderParseError):
        selection.provider.complete(messages=_messages(), temperature=0.0)
    assert "fake" not in repr(selection.provider)


def test_429_recovers_with_bounded_backoff_and_exhaustion_is_typed() -> None:
    sleeps: list[float] = []
    opener = LocalOpener(
        [
            StubResponse(429, {"error": "rate limited"}),
            StubResponse(429, {}),
            StubResponse(200, {"message": {"content": "ok"}}),
        ]
    )
    selection = create_llm_provider(
        LLMConfig(provider="ollama", ollama_base_url="http://local.test")
    )
    selection.provider.transport = _transport(opener, attempts=3, sleeper=sleeps.append)
    assert selection.provider.complete(messages=_messages(), temperature=0.0).content == "ok"
    assert sleeps == [0.25, 0.5]

    exhausted = LocalOpener([StubResponse(429, {}) for _ in range(2)])
    selection.provider.transport = _transport(exhausted, attempts=2)
    with pytest.raises(ProviderRateLimitError):
        selection.provider.complete(messages=_messages(), temperature=0.0)
    assert len(exhausted.requests) == 2


def test_timeout_and_explicit_http_failure_are_safe() -> None:
    timeout = LocalOpener([StubResponse(200, {}, delay=2.0)])
    selection = _selected_provider(LLMConfig(provider="openai"), timeout)
    with pytest.raises(ProviderTimeoutError) as caught:
        selection.provider.complete(messages=_messages(), temperature=0.0)
    assert "offline-secret" not in str(caught.value)

    failed = LocalOpener([StubResponse(401, {"error": "bad key"})])
    selection.provider.transport = _transport(failed)
    with pytest.raises(ProviderTransportError) as caught:
        selection.provider.complete(messages=_messages(), temperature=0.0)
    assert "offline-openai" not in str(caught.value)


def test_generation_metrics_are_skipped_for_fake_and_enabled_with_real_evidence() -> None:
    fake = EvaluationEngine(target=object(), threshold=0).run()
    assert fake.metrics["faithfulness"].reason == "skipped: no_real_provider"
    assert fake.metrics["answer_correctness"].reason == "skipped: no_real_provider"

    real = EvaluationEngine(
        target=object(),
        threshold=0,
        provider_real=True,
        generation_metrics={"faithfulness": 0.9, "answer_correctness": 0.8},
    ).run()
    assert real.metrics["faithfulness"].value == 0.9
    assert real.metrics["answer_correctness"].value == 0.8
