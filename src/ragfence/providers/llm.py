"""HTTP JSON LLM providers with strict, vendor-specific mapping.

No vendor SDK is imported.  The transport seam is injectable so tests use local
request doubles and importing this module never performs network I/O.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ragfence.core.models import LLMResponse, Message

from .tokens import estimate_prompt_tokens, estimate_tokens


class ProviderError(RuntimeError):
    """Safe provider failure; secrets and response bodies are never included."""


class ProviderParseError(ProviderError):
    """The provider returned malformed JSON or an invalid schema."""


class ProviderTransportError(ProviderError):
    """The provider could not be reached or returned an unsuccessful status."""


class ProviderRateLimitError(ProviderTransportError):
    """The provider remained rate limited after bounded retries."""


class ProviderTimeoutError(ProviderTransportError):
    """The provider timed out after bounded retries."""


class _HTTPResponse(Protocol):
    status: int

    def __enter__(self) -> _HTTPResponse: ...
    def __exit__(self, *args: object) -> None: ...
    def read(self) -> bytes: ...


class _Transport(Protocol):
    def post_json(self, path: str, payload: object, headers: Mapping[str, str]) -> object: ...


class LLMHTTPTransport:
    """Small stdlib JSON transport used by real providers."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        opener: Callable[[Request, float], _HTTPResponse] | None = None,
        max_attempts: int = 1,
        backoff: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        if max_attempts < 1 or backoff < 0 or not math.isfinite(backoff):
            raise ValueError("retry settings are invalid")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self._sleeper = sleeper
        self._opener = opener or cast(Callable[[Request, float], _HTTPResponse], urlopen)

    def post_json(self, path: str, payload: object, headers: Mapping[str, str]) -> object:
        url = urljoin(self.base_url, path.lstrip("/"))
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **headers,
        }
        request = Request(url, data=body, headers=request_headers, method="POST")
        for attempt in range(self.max_attempts):
            try:
                with self._opener(request, self.timeout) as response:
                    status = response.status
                    if status == 429:
                        if attempt + 1 < self.max_attempts:
                            self._sleeper(self.backoff * (2**attempt))
                            continue
                        raise ProviderRateLimitError("provider rate limit exhausted")
                    if not 200 <= status < 300:
                        raise ProviderTransportError(f"provider returned HTTP {status}")
                    raw = response.read()
            except HTTPError as exc:
                if exc.code == 429 and attempt + 1 < self.max_attempts:
                    self._sleeper(self.backoff * (2**attempt))
                    continue
                if exc.code == 429:
                    raise ProviderRateLimitError("provider rate limit exhausted") from None
                raise ProviderTransportError(f"provider returned HTTP {exc.code}") from None
            except TimeoutError as exc:
                if attempt + 1 < self.max_attempts:
                    self._sleeper(self.backoff * (2**attempt))
                    continue
                raise ProviderTimeoutError("provider request timed out") from exc
            except (OSError, URLError) as exc:
                raise ProviderTransportError("provider request failed") from exc
            try:
                return json.loads(raw)
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ProviderParseError("provider response was not JSON") from exc
        raise ProviderTransportError("provider request failed")


def _usage(value: object, key: str, fallback: int) -> int:
    if not isinstance(value, Mapping) or key not in value:
        return fallback
    count = value[key]
    if type(count) is not int or count < 0:
        raise ProviderParseError("provider usage was invalid")
    return count


def _messages_payload(messages: list[Message]) -> list[dict[str, str]]:
    return [{"role": message.role, "content": message.content} for message in messages]


class _BaseProvider:
    name = "real"

    def __init__(
        self,
        *,
        model: str,
        transport: _Transport | None,
        base_url: str,
        timeout: float,
        max_attempts: int = 1,
        backoff: float = 0.0,
    ) -> None:
        if not model:
            raise ValueError("model must be non-empty")
        self.model = model
        self.transport = transport or LLMHTTPTransport(
            base_url, timeout=timeout, max_attempts=max_attempts, backoff=backoff
        )

    @staticmethod
    def _prompt_count(messages: list[Message]) -> int:
        return estimate_prompt_tokens([message.content for message in messages])


class OpenAIProvider(_BaseProvider):
    """OpenAI-compatible chat completion provider."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com",
        timeout: float = 10.0,
        transport: _Transport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required")
        super().__init__(model=model, transport=transport, base_url=base_url, timeout=timeout)
        self._api_key = api_key

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": _messages_payload(messages),
            "temperature": temperature,
        }
        raw = self.transport.post_json(
            "/v1/chat/completions", payload, {"Authorization": f"Bearer {self._api_key}"}
        )
        if not isinstance(raw, Mapping):
            raise ProviderParseError("OpenAI response schema was invalid")
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
            raise ProviderParseError("OpenAI response schema was invalid")
        message = choices[0].get("message")
        if not isinstance(message, Mapping) or type(message.get("content")) is not str:
            raise ProviderParseError("OpenAI response schema was invalid")
        content = cast(str, message["content"])
        return LLMResponse(
            content=content,
            prompt_tokens=_usage(raw.get("usage"), "prompt_tokens", self._prompt_count(messages)),
            completion_tokens=_usage(
                raw.get("usage"), "completion_tokens", estimate_tokens(content)
            ),
        )


class AnthropicProvider(_BaseProvider):
    """Anthropic Messages API provider."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-3-5-sonnet-latest",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 10.0,
        max_tokens: int = 1024,
        anthropic_version: str = "2023-06-01",
        transport: _Transport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Anthropic API key is required")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        super().__init__(model=model, transport=transport, base_url=base_url, timeout=timeout)
        self._api_key, self.max_tokens, self.anthropic_version = (
            api_key,
            max_tokens,
            anthropic_version,
        )

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse:
        system = "\n".join(message.content for message in messages if message.role == "system")
        payload: dict[str, object] = {
            "model": self.model,
            "messages": _messages_payload([m for m in messages if m.role != "system"]),
            "max_tokens": self.max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        raw = self.transport.post_json(
            "/v1/messages",
            payload,
            {"x-api-key": self._api_key, "anthropic-version": self.anthropic_version},
        )
        if not isinstance(raw, Mapping) or not isinstance(raw.get("content"), list):
            raise ProviderParseError("Anthropic response schema was invalid")
        blocks = raw["content"]
        texts: list[str] = []
        for block in blocks:
            if (
                not isinstance(block, Mapping)
                or block.get("type") != "text"
                or type(block.get("text")) is not str
            ):
                raise ProviderParseError("Anthropic response schema was invalid")
            texts.append(cast(str, block["text"]))
        content = "".join(texts)
        usage = raw.get("usage")
        return LLMResponse(
            content=content,
            prompt_tokens=_usage(usage, "input_tokens", self._prompt_count(messages)),
            completion_tokens=_usage(usage, "output_tokens", estimate_tokens(content)),
        )


class OllamaProvider(_BaseProvider):
    """Local Ollama chat provider; cloud credentials are not required."""

    name = "ollama"

    def __init__(
        self,
        *,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        timeout: float = 10.0,
        transport: _Transport | None = None,
    ) -> None:
        super().__init__(model=model, transport=transport, base_url=base_url, timeout=timeout)

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": _messages_payload(messages),
            "stream": False,
            "options": {"temperature": temperature},
        }
        raw = self.transport.post_json("/api/chat", payload, {})
        if not isinstance(raw, Mapping) or not isinstance(raw.get("message"), Mapping):
            raise ProviderParseError("Ollama response schema was invalid")
        message = raw["message"]
        if type(message.get("content")) is not str:
            raise ProviderParseError("Ollama response schema was invalid")
        content = cast(str, message["content"])
        return LLMResponse(
            content=content,
            prompt_tokens=_usage(raw, "prompt_eval_count", self._prompt_count(messages)),
            completion_tokens=_usage(raw, "eval_count", estimate_tokens(content)),
        )


class LLMConfigurationError(ValueError):
    """Safe configuration failure; secret values are never included."""


class LLMConfig(BaseModel):
    """Typed settings for the ``[llm]`` configuration section."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["fake", "openai", "anthropic", "ollama", "auto"] = "fake"
    model: str | None = None
    temperature: float = 0.0
    timeout: float = 30.0
    max_retries: int = 0
    backoff: float = 0.25
    openai_base_url: str = "https://api.openai.com"
    anthropic_base_url: str = "https://api.anthropic.com"
    ollama_base_url: str = "http://127.0.0.1:11434"
    openai_api_key: SecretStr | None = Field(default=None, repr=False)
    anthropic_api_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator("temperature", "timeout", "backoff")
    @classmethod
    def finite_non_negative(cls, value: float) -> float:
        if not math.isfinite(value) or value < 0:
            raise ValueError("must be finite and non-negative")
        return value

    @field_validator("max_retries")
    @classmethod
    def bounded_retries(cls, value: int) -> int:
        if value < 0 or value > 10:
            raise ValueError("must be between 0 and 10")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def valid_ollama_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
        ):
            raise ValueError("ollama_base_url must be an http(s) URL without credentials")
        return value.rstrip("/")

    @property
    def timeout_seconds(self) -> float:
        """Compatibility spelling for callers using seconds explicitly."""

        return self.timeout

    def model_for(self, provider: str) -> str:
        defaults = {
            "fake": "fake",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-latest",
            "ollama": "llama3",
        }
        return self.model or defaults[provider]


class _LLMProvider(Protocol):
    name: str

    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse: ...


@dataclass(frozen=True)
class LLMSelection:
    """Provider plus non-secret metadata suitable for reports."""

    provider: _LLMProvider
    metadata: dict[str, str | bool]


def _secret(configured: SecretStr | None, name: str, environment: Mapping[str, str]) -> str | None:
    value = environment.get(name)
    if value and value.strip():
        return value
    return configured.get_secret_value() if configured is not None else None


def create_llm_provider(
    config: LLMConfig, *, environ: Mapping[str, str] | None = None
) -> LLMSelection:
    """Select a provider without performing a completion or network request."""

    environment = os.environ if environ is None else environ
    requested = config.provider
    if requested == "auto":
        if _secret(config.openai_api_key, "OPENAI_API_KEY", environment):
            requested = "openai"
        elif _secret(config.anthropic_api_key, "ANTHROPIC_API_KEY", environment):
            requested = "anthropic"
        else:
            requested = "fake"
    model = config.model_for(requested)
    metadata: dict[str, str | bool] = {
        "provider": requested,
        "real": requested != "fake",
        "model": model,
    }
    if requested == "fake":
        from ragfence.providers.fakes import FakeLLMProvider

        return LLMSelection(FakeLLMProvider(), metadata)
    if requested == "ollama":
        return LLMSelection(
            OllamaProvider(model=model, base_url=config.ollama_base_url, timeout=config.timeout),
            metadata,
        )
    key_name = "OPENAI_API_KEY" if requested == "openai" else "ANTHROPIC_API_KEY"
    key = _secret(
        config.openai_api_key if requested == "openai" else config.anthropic_api_key,
        key_name,
        environment,
    )
    if not key:
        raise LLMConfigurationError(f"{requested} provider requires {key_name}")
    provider: _LLMProvider
    if requested == "openai":
        provider = OpenAIProvider(
            api_key=key, model=model, base_url=config.openai_base_url, timeout=config.timeout
        )
    else:
        provider = AnthropicProvider(
            api_key=key, model=model, base_url=config.anthropic_base_url, timeout=config.timeout
        )
    return LLMSelection(provider, metadata)


llm_provider_factory = create_llm_provider


# configuration and selection are defined above

# end of module


__all__ = [
    "AnthropicProvider",
    "LLMConfig",
    "LLMConfigurationError",
    "LLMHTTPTransport",
    "LLMSelection",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderError",
    "ProviderParseError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderTransportError",
    "create_llm_provider",
]
