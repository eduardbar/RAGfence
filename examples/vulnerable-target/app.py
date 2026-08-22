"""A deliberately vulnerable, deterministic RAG target for the RAGFence tutorial."""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Header

app = FastAPI(title="RAGFence vulnerable demo")

# Stable IDs make tutorial output and tests reproducible.
CORPUS: list[dict[str, Any]] = [
    {
        "chunk_id": "00000000-0000-4000-8000-000000000001",
        "document_id": "00000000-0000-4000-8000-000000000011",
        "document_title": "Acme billing policy",
        "chunk_index": 0,
        "content": "Acme quarterly billing is approved by the finance team.",
        "tenant": "acme",
    },
    {
        "chunk_id": "00000000-0000-4000-8000-000000000002",
        "document_id": "00000000-0000-4000-8000-000000000012",
        "document_title": "Globex restricted billing memo",
        "chunk_index": 0,
        "content": "Globex quarterly billing secret: customer discount is 42 percent.",
        "tenant": "globex",
    },
    {
        "chunk_id": "00000000-0000-4000-8000-000000000003",
        "document_id": "00000000-0000-4000-8000-000000000013",
        "document_title": "Acme travel policy",
        "chunk_index": 0,
        "content": "Acme travel expenses require a manager review.",
        "tenant": "acme",
    },
    {
        "chunk_id": "00000000-0000-4000-8000-000000000004",
        "document_id": "00000000-0000-4000-8000-000000000014",
        "document_title": "Globex travel policy",
        "chunk_index": 0,
        "content": "Globex travel expenses require a director review.",
        "tenant": "globex",
    },
]


def _search(question: str, top_k: int) -> list[dict[str, Any]]:
    terms = set(re.findall(r"[a-z0-9]+", question.lower()))
    scored = []
    for position, document in enumerate(CORPUS):
        words = set(re.findall(r"[a-z0-9]+", document["content"].lower()))
        score = len(terms & words) / max(len(terms), 1)
        scored.append((score, -position, document))
    scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [{**document, "score": float(score)} for score, _, document in scored[:top_k]]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/retrieve")
def retrieve(
    body: dict[str, Any],
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> dict[str, list[dict[str, Any]]]:
    question = str(body.get("question", ""))
    top_k = max(1, min(int(body.get("top_k", 10)), 50))
    tenant = x_tenant_id or "acme"  # BUG: authorization is an untrusted header.

    # DELIBERATE BUG: retrieval happens across tenants before authorization filtering.
    ranked = _search(question, top_k)
    # The attempted filter is misapplied: the globex branch bypasses tenant isolation.
    visible = [
        document
        for document in ranked
        if document["tenant"] == tenant or document["tenant"] == "globex"
    ]
    return {
        "chunks": [
            {
                key: document[key]
                for key in (
                    "chunk_id",
                    "document_id",
                    "document_title",
                    "chunk_index",
                    "content",
                    "score",
                )
            }
            | {"metadata": {"tenant": document["tenant"]}}
            for document in visible
        ]
    }
