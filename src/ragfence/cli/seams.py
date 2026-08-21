"""Injectable runtime seams used by the Phase 6 CLI."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol, cast

from sqlalchemy import create_engine, text

from ragfence.adapters import create_adapter
from ragfence.adapters.reference import ReferenceAdapter
from ragfence.attacks.runner import ScenarioTarget
from ragfence.cli.config import CliConfig
from ragfence.cli.errors import RuntimeCommandError
from ragfence.cli.reporting import EvaluationReport
from ragfence.core.models import RetrievalRequest, RetrievedChunk


def canonical_threshold(legacy_threshold: float) -> float:
    """Translate the public CLI's legacy 0–1 threshold to the engine's 0–100 scale."""
    if not 0 <= legacy_threshold <= 1:
        raise ValueError("threshold must be a number between 0 and 1")
    return legacy_threshold * 100.0


class _ReferenceTarget:
    """Deterministic local target used until an adapter is wired in."""

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]:
        del request
        return []

    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str:
        del request, chunks
        return "blocked"


class _ExternalAdapter(ScenarioTarget, Protocol):
    """Runtime shape required by the evaluation engine for external adapters."""

    name: str

    def is_healthy(self) -> bool: ...

    def check_identity_represented(self) -> bool: ...


def _target_for(config: CliConfig, name: str) -> ScenarioTarget:
    if name == "reference":
        dsn = os.environ.get(
            "RAGFENCE_DATABASE_DSN",
            "postgresql+psycopg://ragfence:ragfence@localhost:5434/ragfence",
        )
        return cast(ScenarioTarget, ReferenceAdapter(create_engine(dsn)))
    if name == "generic_http":
        if config.generic_http is None:
            raise RuntimeCommandError(
                "external adapter target is unavailable; configure adapters.generic_http"
            )
        return cast(_ExternalAdapter, create_adapter(name, config.generic_http))
    raise RuntimeCommandError(f"unsupported adapter: {name}")


def evaluate(
    config: CliConfig,
    *,
    adapter: str | None,
    base_url: str | None,
) -> EvaluationReport:
    """Run the configured reference or generic HTTP target."""
    requested_adapter = config.adapter if adapter is None else adapter
    if requested_adapter == "reference" and base_url is not None:
        raise RuntimeCommandError(
            "external adapter target is unavailable; configure the reference target instead"
        )

    threshold = canonical_threshold(config.threshold)

    from ragfence.attacks.generators import default_evaluation_controls
    from ragfence.evaluation.gate import evaluate_gate
    from ragfence.evaluation.matrix_runner import run_matrix

    if requested_adapter == "reference":
        dsn = os.environ.get(
            "RAGFENCE_DATABASE_DSN",
            "postgresql+psycopg://ragfence:ragfence@localhost:5434/ragfence",
        )
        engine = create_engine(dsn)
        target: ReferenceAdapter | _ExternalAdapter = ReferenceAdapter(engine)
        identity_represented_for = None
    elif requested_adapter == "generic_http":
        if config.generic_http is None:
            raise RuntimeCommandError(
                "external adapter target is unavailable; configure adapters.generic_http"
            )
        http_adapter = cast(
            _ExternalAdapter, create_adapter(requested_adapter, config.generic_http)
        )
        target = http_adapter

        def identity_represented_for(_c: object) -> bool:
            return bool(http_adapter.check_identity_represented())
    else:
        raise RuntimeCommandError(f"unsupported adapter: {requested_adapter}")

    controls = default_evaluation_controls()
    results = run_matrix(target, controls, identity_represented_for=identity_represented_for)
    decision = evaluate_gate(results, controls, threshold=threshold)

    payload = {
        "controls": [
            {
                "id": result.control.id,
                "category": result.control.category,
                "status": result.status,
                "reason": result.reason,
            }
            for result in results
        ],
        "security_score": decision.security_score,
        "utility_score": decision.utility_score,
        "overall_score": decision.overall_score,
        "gate_passed": decision.passed,
        "gate_reason": list(decision.reasons),
        "score": decision.overall_score * 100,
        "threshold": threshold,
        "outcome": "pass" if decision.passed else "fail",
        "real_provider_used": False,
        "results": [
            {
                "case_id": result.control.id,
                "scenario_id": result.control.id,
                "passed": result.status == "pass",
                "outcome": result.status,
                "reason": result.reason,
                "findings": [],
                "retrieved": [],
                "answer": None,
                "latency_ms": result.observation.latency_ms,
            }
            for result in results
        ],
    }

    return EvaluationReport(
        score=float(payload["score"]),  # type: ignore[arg-type]
        threshold=threshold,
        outcome=str(payload["outcome"]),
        findings=[],
        artifact=payload,
    )


def check_demo(config: CliConfig, *, start: bool) -> None:
    """Check or start the future reference demo service."""
    del config, start
    raise RuntimeCommandError("reference demo service is unavailable")


def check_adapter(
    config: CliConfig,
    *,
    name: str,
    base_url: str | None,
) -> None:
    """Validate and check reachability of a configured adapter."""
    del base_url
    if name == "reference":
        dsn = os.environ.get(
            "RAGFENCE_DATABASE_DSN",
            "postgresql+psycopg://ragfence:ragfence@localhost:5434/ragfence",
        )
        try:
            engine = create_engine(dsn, connect_args={"connect_timeout": 2})
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            from sqlalchemy import inspect

            insp = inspect(engine)
            if "alembic_version" in insp.get_table_names():
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT version_num FROM alembic_version"))
                    version = result.scalar()
                    if not version:
                        raise RuntimeCommandError("alembic version not found")
            with engine.connect() as conn:
                tenant_count = conn.execute(text("SELECT COUNT(*) FROM tenants")).scalar()
                doc_count = conn.execute(text("SELECT COUNT(*) FROM documents")).scalar()
                user_count = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            if tenant_count is None or tenant_count < 2:
                raise RuntimeCommandError(f"insufficient tenants seeded: {tenant_count}")
            if doc_count == 0:
                raise RuntimeCommandError("no documents seeded")
            if user_count == 0:
                raise RuntimeCommandError("no users seeded")
            engine.dispose()
        except Exception as exc:
            if isinstance(exc, RuntimeCommandError):
                raise
            raise RuntimeCommandError(f"reference adapter target is unavailable: {exc}") from exc
        return
    adapter = cast(_ExternalAdapter, create_adapter(name, config.generic_http))
    if not adapter.is_healthy():
        raise RuntimeCommandError(f"adapter unhealthy: {name}")


def default_report_path(config_path: Path, *, json_output: bool) -> Path:
    """Return the default report destination beside the config file."""
    suffix = ".json" if json_output else ".txt"
    return config_path.parent / ".ragfence" / "reports" / f"latest{suffix}"
