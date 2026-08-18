"""Injectable runtime seams used by the Phase 6 CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

from ragfence.adapters import create_adapter
from ragfence.attacks.runner import ScenarioTarget
from ragfence.cli.config import CliConfig
from ragfence.cli.errors import RuntimeCommandError
from ragfence.cli.reporting import EvaluationReport
from ragfence.core.models import RetrievalRequest, RetrievedChunk
from ragfence.evaluation.engine import EvaluationEngine
from ragfence.evaluation.report import build_report


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


def _target_for(config: CliConfig, name: str) -> ScenarioTarget:
    if name == "reference":
        return _ReferenceTarget()
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
    target = _target_for(config, requested_adapter)
    summary = EvaluationEngine(target, threshold=threshold).run()
    artifact = build_report(summary, summary.results)
    payload = artifact.payload
    outcome = payload.get("outcome", "")
    return EvaluationReport(
        score=float(payload.get("score", 0.0)),
        threshold=float(payload.get("threshold", threshold)),
        outcome=str(getattr(outcome, "value", outcome)),
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
        raise RuntimeCommandError("reference adapter target is unavailable")
    adapter = cast(_ExternalAdapter, create_adapter(name, config.generic_http))
    if not adapter.is_healthy():
        raise RuntimeCommandError(f"adapter unhealthy: {name}")


def default_report_path(config_path: Path, *, json_output: bool) -> Path:
    """Return the default report destination beside the config file."""
    suffix = ".json" if json_output else ".txt"
    return config_path.parent / ".ragfence" / "reports" / f"latest{suffix}"
