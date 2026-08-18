"""Offline validation of checked-in reference and generic HTTP examples."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from uuid import UUID

from ragfence.adapters.generic_http import (
    GenericHTTPAdapter,
    GenericHTTPConfig,
    GenericHTTPTransport,
)
from ragfence.cli.config import load_config
from ragfence.core.enums import Classification
from ragfence.core.models import AuthorizationContext, RetrievalRequest
from tests.support.generic_http_stub import GenericHTTPStub, json_response

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{36,}"),
)
CHUNK = {
    "chunk_id": "00000000-0000-0000-0000-000000000001",
    "document_id": "00000000-0000-0000-0000-000000000002",
    "document_title": "Example",
    "chunk_index": 0,
    "content": "Example content.",
    "score": 1.0,
    "metadata": {},
}
REQUEST = RetrievalRequest(
    query="example",
    top_k=1,
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


def test_reference_example_loads_without_network() -> None:
    path = EXAMPLES / "reference.toml"
    with path.open("rb") as stream:
        parsed = tomllib.load(stream)
    assert parsed["adapter"] == "reference"
    assert parsed["database"]["dsn"].startswith("postgresql+psycopg://")
    assert "CHANGEME" in parsed["database"]["dsn"]
    assert load_config(path).adapter == "reference"


def test_generic_http_example_has_safe_bounded_contract() -> None:
    path = EXAMPLES / "generic_http.toml"
    with path.open("rb") as stream:
        parsed = tomllib.load(stream)
    values = parsed["adapters"]["generic_http"]
    config = GenericHTTPConfig.model_validate(values)
    loaded = load_config(path)
    assert loaded.adapter == "generic_http"
    assert loaded.generic_http is not None
    assert loaded.generic_http.base_url == "http://localhost:8000"
    assert config.base_url == "http://localhost:8000"
    assert config.retrieve_path == "retrieve"
    assert config.health_path == "health"
    assert 0 < config.timeout_seconds <= 30
    assert 0 <= config.health_retries <= 10
    assert 0 <= config.health_backoff_seconds <= 60
    assert config.auth_token == "CHANGEME"


def test_generic_http_example_works_with_deterministic_stub() -> None:
    with (EXAMPLES / "generic_http.toml").open("rb") as stream:
        values = tomllib.load(stream)["adapters"]["generic_http"]
    stub = GenericHTTPStub()
    stub.route("GET", "/health", json_response({"status": "ok"}))
    stub.route("POST", "/retrieve", json_response({"chunks": [CHUNK]}))
    config = GenericHTTPConfig.model_validate({**values, "base_url": stub.base_url})
    adapter = GenericHTTPAdapter(config, transport=GenericHTTPTransport(config, opener=stub))
    assert adapter.is_healthy() is True
    assert adapter.retrieve(REQUEST)[0].content == CHUNK["content"]


def test_example_configs_contain_no_secret_shaped_values() -> None:
    for path in EXAMPLES.glob("*.toml"):
        text = path.read_text(encoding="utf-8")
        assert "password" not in text.lower() or "CHANGEME" in text
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(text), f"{path.name} contains a real-looking secret"
