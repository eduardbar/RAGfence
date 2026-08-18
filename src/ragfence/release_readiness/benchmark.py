"""Deterministic Acme performance sanity check.

This is a bounded local baseline for regression detection only. It is not a
production capacity or hosting claim.
"""

from __future__ import annotations

import os
import platform
import statistics
import time
from typing import Any

from ragfence.datasets import build_acme_corp
from ragfence.providers.fakes import FakeEmbeddingProvider

# Reviewable local sanity budget, deliberately not a production SLO.
LOCAL_BASELINE = {
    "kind": "local_sanity_baseline",
    "search_p95_ms": 500.0,
    "production_claim": False,
    "notes": "Single-process CPython, bounded five-document corpus; regression guard only.",
}


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    return float(numerator / (left_norm * right_norm))


def run_acme_benchmark(*, repetitions: int = 20) -> dict[str, Any]:
    """Measure local fake embedding and authorized in-memory search seams."""
    if repetitions < 5:
        raise ValueError("repetitions must be at least 5")
    setup_start = time.perf_counter()
    dataset = build_acme_corp()
    embedder = FakeEmbeddingProvider()
    vectors = {path: embedder.embed([doc.body])[0] for path, doc in dataset.documents.items()}
    setup_ms = (time.perf_counter() - setup_start) * 1000

    queries = tuple(dataset.users)
    search_samples: list[float] = []
    unauthorized = 0
    errors = 0
    for _ in range(repetitions):
        for email in queries:
            try:
                context = dataset.context_for(email)
                start = time.perf_counter()
                ranked = sorted(
                    dataset.documents,
                    key=lambda path: _cosine(vectors[path], vectors[next(iter(vectors))]),
                    reverse=True,
                )
                allowed = [
                    path
                    for path in ranked
                    if dataset.documents[path].acl.tenant_id == context.tenant_id
                    and (
                        dataset.documents[path].acl.department_id == context.department_id
                        or bool(
                            set(dataset.documents[path].acl.allowed_group_ids)
                            & context.allowed_group_ids
                        )
                        or dataset.documents[path].classification.value == "public"
                    )
                ]
                search_samples.append((time.perf_counter() - start) * 1000)
                unauthorized += sum(
                    1 for path in allowed if dataset.documents[path].tenant_id != context.tenant_id
                )
            except Exception:
                errors += 1

    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "provider": "fake",
            "network": "not used",
        },
        "corpus_documents": len(dataset.documents),
        "query_count": len(queries),
        "repetitions": repetitions,
        "embedding_setup_ms": round(setup_ms, 3),
        "search_ms": {
            "p50": round(statistics.median(search_samples), 3),
            "p95": round(sorted(search_samples)[max(0, int(len(search_samples) * 0.95) - 1)], 3),
        },
        "errors": errors,
        "unauthorized_retrievals": unauthorized,
        "baseline": dict(LOCAL_BASELINE),
        "process": os.getpid(),
    }
