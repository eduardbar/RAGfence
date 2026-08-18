"""Configuration contract tests for the generic HTTP adapter."""

from pathlib import Path

import pytest

from ragfence.cli.config import ConfigError, load_config


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "ragfence.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_loads_generic_http_defaults_and_nested_toml(tmp_path: Path) -> None:
    config = load_config(
        _write(
            tmp_path,
            """
[adapters.generic_http]
base_url = "https://rag.example.test/api"
retrieve_path = "retrieve"
""",
        ),
        environ={},
    )

    assert config.generic_http is not None
    assert config.generic_http.base_url == "https://rag.example.test/api"
    assert config.generic_http.retrieve_path == "retrieve"
    assert config.generic_http.answer_path is None
    assert config.generic_http.health_path == "health"
    assert config.generic_http.timeout_seconds == 10.0
    assert config.generic_http.health_retries == 3
    assert config.generic_http.health_backoff_seconds == 0.25
    assert config.generic_http.auth_token is None


@pytest.mark.parametrize(
    "field, value",
    [
        ("base_url", "ftp://rag.example.test"),
        ("base_url", "not a url"),
        ("retrieve_path", "https://evil.example/retrieve"),
        ("retrieve_path", "/retrieve"),
        ("answer_path", "//evil.example/answer"),
        ("timeout_seconds", "nan"),
        ("timeout_seconds", "0"),
        ("health_retries", "-1"),
        ("health_retries", "11"),
        ("health_backoff_seconds", "-0.1"),
        ("health_backoff_seconds", "nan"),
    ],
)
def test_rejects_unsafe_or_unbounded_values(tmp_path: Path, field: str, value: str) -> None:
    config = (
        "[adapters.generic_http]\n"
        'base_url = "https://rag.example.test"\n'
        'retrieve_path = "retrieve"\n'
        f'{field} = "{value}"\n'
    )

    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, config), environ={})


def test_cli_base_url_override_is_validated_and_applied(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[adapters.generic_http]\nbase_url = "https://file.example"\nretrieve_path = "retrieve"\n',
    )

    loaded = load_config(path, environ={}, base_url_override="http://cli.example/v1")

    assert loaded.generic_http is not None
    assert loaded.generic_http.base_url == "http://cli.example/v1"


def test_static_auth_rejects_header_injection_and_empty_token(tmp_path: Path) -> None:
    for auth in (
        'auth_header = "X-Token\\r\\nInjected"\nauth_token = "secret"',
        'auth_header = "Authorization"\nauth_token = ""',
    ):
        body = (
            '[adapters.generic_http]\nbase_url = "https://rag.example"\n'
            f'retrieve_path = "retrieve"\n{auth}\n'
        )
        with pytest.raises(ConfigError):
            load_config(_write(tmp_path, body), environ={})
