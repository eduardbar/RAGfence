"""RED tests for typed LLM configuration and provider selection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ragfence.providers.fakes import FakeLLMProvider
from ragfence.providers.llm import (
    AnthropicProvider,
    LLMConfig,
    LLMConfigurationError,
    OllamaProvider,
    OpenAIProvider,
    create_llm_provider,
)


def test_default_configuration_selects_non_real_fake_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    selection = create_llm_provider(LLMConfig())

    assert isinstance(selection.provider, FakeLLMProvider)
    assert selection.metadata == {"provider": "fake", "real": False, "model": "fake"}


@pytest.mark.parametrize(
    ("provider_name", "provider_type"),
    [
        ("fake", FakeLLMProvider),
        ("openai", OpenAIProvider),
        ("anthropic", AnthropicProvider),
        ("ollama", OllamaProvider),
    ],
)
def test_explicit_provider_is_selected(
    provider_name: str, provider_type: type[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "open-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")

    selection = create_llm_provider(LLMConfig(provider=provider_name))

    assert isinstance(selection.provider, provider_type)
    assert selection.metadata["provider"] == provider_name
    assert selection.metadata["real"] is (provider_name != "fake")


def test_explicit_keyed_provider_without_key_fails_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(LLMConfigurationError, match="OPENAI_API_KEY") as raised:
        create_llm_provider(LLMConfig(provider="openai"))

    assert "open-secret" not in str(raised.value)


def test_anthropic_missing_key_error_is_secret_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(LLMConfigurationError, match="ANTHROPIC_API_KEY"):
        create_llm_provider(LLMConfig(provider="anthropic"))


def test_ollama_base_url_is_validated() -> None:
    with pytest.raises(ValidationError):
        LLMConfig(provider="ollama", ollama_base_url="not-a-url")

    with pytest.raises(ValidationError):
        LLMConfig(provider="ollama", ollama_base_url="file:///tmp/ollama")


def test_ollama_has_safe_local_default_and_no_key_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    selection = create_llm_provider(LLMConfig(provider="ollama"))

    assert isinstance(selection.provider, OllamaProvider)
    assert selection.metadata == {"provider": "ollama", "real": True, "model": "llama3"}


def test_byok_reads_environment_and_never_exposes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "open-secret-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    selection = create_llm_provider(LLMConfig(provider="openai"))

    assert selection.metadata == {"provider": "openai", "real": True, "model": "gpt-4o-mini"}
    assert secret not in repr(selection.metadata)
    assert secret not in repr(selection.provider)


def test_injected_environment_overrides_configured_secret() -> None:
    configured = "config-secret"
    injected = "environment-secret"
    selection = create_llm_provider(
        LLMConfig(provider="openai", openai_api_key=configured),
        environ={"OPENAI_API_KEY": injected},
    )

    assert injected == selection.provider._api_key
    assert configured not in repr(selection.provider)
    assert injected not in repr(selection.provider)


def test_invalid_provider_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMConfig(provider="wat")
