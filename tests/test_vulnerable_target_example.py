"""Regression tests for the intentionally vulnerable tutorial target."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

_APP = Path(__file__).parents[1] / "examples" / "vulnerable-target" / "app.py"
_SPEC = spec_from_file_location("vulnerable_target_app", _APP)
assert _SPEC and _SPEC.loader
_APP_MODULE = module_from_spec(_SPEC)
_SPEC.loader.exec_module(_APP_MODULE)


def test_target_serves_generic_http_retrieve_contract() -> None:
    response = TestClient(_APP_MODULE.app).post(
        "/retrieve", json={"question": "quarterly billing", "top_k": 2}
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"chunks"}
    assert payload["chunks"]
    assert {
        "chunk_id",
        "document_id",
        "document_title",
        "chunk_index",
        "content",
        "score",
        "metadata",
    } <= set(payload["chunks"][0])


def test_acme_default_tenant_leaks_globex_document() -> None:
    response = TestClient(_APP_MODULE.app).post(
        "/retrieve",
        json={"question": "globex quarterly billing secret", "top_k": 10},
        headers={"X-Tenant-ID": "acme"},
    )

    assert response.status_code == 200
    chunks = response.json()["chunks"]
    assert any(chunk["metadata"]["tenant"] == "globex" for chunk in chunks)
    assert any("Globex" in chunk["content"] for chunk in chunks)
