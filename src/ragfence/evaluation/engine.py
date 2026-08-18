"""Deterministic, in-memory orchestration for Phase 7 evaluations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from ragfence.attacks.generators import generate_cases
from ragfence.attacks.runner import (
    ScenarioObservation,
    ScenarioTarget,
    ScenarioVerdict,
    run_case,
)
from ragfence.core.enums import ScenarioOutcome
from ragfence.core.models import EvaluationCase, RetrievedChunk, SecurityFinding
from ragfence.db.models import RunStatus
from ragfence.evaluation import findings as default_findings
from ragfence.evaluation import metrics as default_metrics
from ragfence.evaluation.contracts import MetricValue
from ragfence.evaluation.redaction import redact_evidence
from ragfence.evaluation.repositories import (
    EvaluationRepository,
    canonical_db_threshold,
    result_identity,
    stable_run_id,
)
from ragfence.evaluation.scoring import calculate_score, passes_threshold


def _result_id(run_identity: UUID, case_id: UUID) -> UUID:
    return result_identity(run_identity, case_id)


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """One stable, in-memory result corresponding to exactly one case."""

    id: UUID
    case_id: UUID
    scenario_id: str
    passed: bool
    outcome: ScenarioOutcome
    reason: str
    findings: tuple[SecurityFinding, ...]
    retrieved: tuple[RetrievedChunk, ...]
    answer: str | None
    error: str | None
    latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": redact_evidence(self.answer),
            "case_id": str(self.case_id),
            "error": redact_evidence(self.error),
            "findings": [finding.model_dump(mode="json") for finding in self.findings],
            "id": str(self.id),
            "latency_ms": self.latency_ms,
            "outcome": self.outcome.value,
            "passed": self.passed,
            "reason": redact_evidence(self.reason),
            "retrieved": [chunk.model_dump(mode="json") for chunk in self.retrieved],
            "scenario_id": self.scenario_id,
        }


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    """Complete deterministic suite summary; no persistence or wall-clock data."""

    seed: int
    threshold: float
    results: tuple[EvaluationResult, ...]
    metrics: Mapping[str, MetricValue]
    latency: Mapping[str, int | float]
    score: float
    outcome: ScenarioOutcome
    passed_threshold: bool

    def to_dict(self) -> dict[str, Any]:
        metric_dict = {
            name: {
                "available": metric.available,
                "name": metric.name,
                "policy": metric.policy.value,
                "reason": metric.reason,
                "value": metric.value,
            }
            for name, metric in sorted(self.metrics.items())
        }
        return {
            "latency": dict(sorted(self.latency.items())),
            "metrics": metric_dict,
            "outcome": self.outcome.value,
            "passed_threshold": self.passed_threshold,
            "results": [
                result.to_dict()
                for result in sorted(self.results, key=lambda item: str(item.case_id))
            ],
            "score": self.score,
            "seed": self.seed,
            "threshold": self.threshold,
        }

    def canonical_bytes(self) -> bytes:
        """Return canonical JSON bytes suitable for fingerprints and comparisons."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PersistedEvaluation:
    """Stable database identities returned by a completed persistence transaction."""

    suite_id: UUID
    run_id: UUID


@dataclass(frozen=True, slots=True)
class ReloadedEvaluation:
    """Rows reloaded for a persisted run, in canonical database order."""

    run: Any
    results: tuple[Any, ...]
    findings: tuple[Any, ...]


class EvaluationEngine:
    """Run a generated suite against an injected target entirely in memory."""

    def __init__(
        self,
        target: ScenarioTarget,
        *,
        seed: int = 2026,
        threshold: float = 80.0,
        findings: Any = None,
        metrics: Any = None,
        relevant_chunk_ids_by_case: Mapping[Any, Any] | None = None,
        leakage_markers: tuple[str, ...] | None = None,
        provider_real: bool = False,
        generation_metrics: Mapping[str, float] | None = None,
        provider_metadata: Mapping[str, object] | None = None,
    ) -> None:
        self.target = target
        self.seed = seed
        self.threshold = threshold
        self.findings = findings or default_findings
        self.metrics = metrics or default_metrics
        self.relevant_chunk_ids_by_case = relevant_chunk_ids_by_case or {}
        self.leakage_markers = leakage_markers or default_findings.DEFAULT_LEAKAGE_MARKERS
        inherited = getattr(target, "provider_metadata", {})
        metadata = provider_metadata or (inherited if isinstance(inherited, Mapping) else {})
        self.provider_real = provider_real or (
            metadata.get("real") is True
            and metadata.get("provider") in {"openai", "anthropic", "ollama"}
        )
        self.provider_metadata = dict(metadata)
        self.generation_metrics = dict(generation_metrics or {})
        for name in ("faithfulness", "answer_correctness"):
            value = metadata.get(name)
            if type(value) is int or type(value) is float:
                self.generation_metrics[name] = float(value)
        self._run_identity = uuid5(NAMESPACE_URL, f"in-memory-run:{seed}:{threshold}")

    def _error_verdict(self, case: EvaluationCase, error: Exception) -> ScenarioVerdict:
        observation = ScenarioObservation(case.id, (), None, str(error), 0)
        return ScenarioVerdict(case, observation, False, f"target error: {error}")

    def _result(self, verdict: ScenarioVerdict) -> EvaluationResult:
        generation_case = verdict.case.scenario_id in {
            "prompt-injection",
            "indirect-prompt-injection",
            "direct-sensitive-data",
            "document-poisoning",
        }
        skipped = generation_case and not self.provider_real and verdict.observation.error is None
        derived = tuple(
            self.findings.derive_findings(
                verdict,
                leakage_markers=self.leakage_markers,
                run_id=self._run_identity,
                generation_skip_reason="skipped: no_real_provider" if skipped else None,
            )
        )
        outcome = self.findings.outcome_for_findings(derived)
        observation = verdict.observation
        return EvaluationResult(
            id=_result_id(self._run_identity, verdict.case.id),
            case_id=verdict.case.id,
            scenario_id=verdict.case.scenario_id,
            passed=verdict.passed and outcome is ScenarioOutcome.PASS,
            outcome=outcome,
            reason=f"{verdict.reason}; skipped: no_real_provider" if skipped else verdict.reason,
            findings=derived,
            retrieved=tuple(observation.retrieved),
            answer=observation.answer,
            error=observation.error,
            latency_ms=max(0, observation.latency_ms),
        )

    def persist(
        self,
        summary: EvaluationSummary,
        session: Session,
        *,
        suite_name: str = "generated-evaluation",
        target_adapter: str | None = None,
        configuration: Mapping[str, Any] | None = None,
    ) -> PersistedEvaluation:
        """Persist a summary atomically through the existing five-table repository.

        The caller supplies a session so transaction ownership is explicit.  All
        writes occur inside one ``Session.begin`` block; failures roll back the
        complete suite/run graph and are re-raised unchanged.
        """
        repository = EvaluationRepository(session)
        adapter = target_adapter or type(self.target).__name__
        cases = {case.id: case for case in generate_cases(seed=summary.seed)}
        case_ids = tuple(result.case_id for result in summary.results)
        run_configuration = dict(configuration or {})
        run_configuration.update({"seed": summary.seed, "threshold": summary.threshold})
        try:
            with session.begin():
                suite = repository.upsert_suite(
                    name=suite_name,
                    description="RAGFence evaluation suite",
                    target_adapter=adapter,
                    threshold=canonical_db_threshold(summary.threshold),
                )
                persisted_case_ids: dict[UUID, UUID] = {}
                for case_id in case_ids:
                    case = cases[case_id]
                    persisted_case = repository.upsert_case(
                        suite_id=suite.id,
                        case_id=case.id,
                        scenario_id=case.scenario_id,
                        prompt=case.prompt,
                        actor=case.actor.model_dump(mode="json"),
                        expected_allow=case.expected_allow,
                    )
                    persisted_case_ids[case_id] = persisted_case.id
                run_id = stable_run_id(suite.id, persisted_case_ids.values(), run_configuration)
                run = repository.upsert_run(
                    suite_id=suite.id,
                    run_id=run_id,
                    status=RunStatus.PASSED if summary.passed_threshold else RunStatus.FAILED,
                    score=Decimal(str(round(summary.score, 2))),
                    threshold=canonical_db_threshold(summary.threshold),
                    outcome=summary.outcome,
                )
                findings: list[dict[str, Any]] = []
                for result in summary.results:
                    persisted_result = repository.upsert_result(
                        run_id=run.id,
                        case_id=persisted_case_ids[result.case_id],
                        result_id=result_identity(run.id, persisted_case_ids[result.case_id]),
                        passed=result.passed,
                        outcome=result.outcome,
                        retrieved_chunk_ids=(chunk.chunk_id for chunk in result.retrieved),
                        answer=redact_evidence(result.answer),
                        latency_ms=result.latency_ms,
                    )
                    findings.extend(
                        {
                            "id": finding.id,
                            "result_id": getattr(persisted_result, "id", result.id),
                            "case_id": persisted_case_ids[result.case_id],
                            "severity": finding.severity,
                            "category": finding.category,
                            "title": finding.title,
                            "description": finding.description,
                            "evidence": finding.evidence,
                        }
                        for finding in result.findings
                    )
                repository.reconcile_findings(run_id=run.id, findings=findings)
            return PersistedEvaluation(suite_id=suite.id, run_id=run.id)
        except Exception:
            session.rollback()
            raise

    def replay(
        self,
        summary: EvaluationSummary,
        session: Session,
        *,
        suite_name: str = "generated-evaluation",
        target_adapter: str | None = None,
        configuration: Mapping[str, Any] | None = None,
    ) -> PersistedEvaluation:
        """Replay the same summary using stable upsert/reconciliation identities."""
        return self.persist(
            summary,
            session,
            suite_name=suite_name,
            target_adapter=target_adapter,
            configuration=configuration,
        )

    def reload(self, session: Session, run_id: UUID) -> ReloadedEvaluation:
        """Reload a persisted run and its ordered results/findings."""
        repository = EvaluationRepository(session)
        run = repository.get_run(run_id)
        if run is None:
            raise KeyError(f"evaluation run not found: {run_id}")
        return ReloadedEvaluation(
            run=run,
            results=tuple(repository.list_results(run_id)),
            findings=tuple(repository.list_findings(run_id)),
        )

    def run(self) -> EvaluationSummary:
        if not 0 <= self.threshold <= 100:
            raise ValueError("threshold must be between 0 and 100")
        cases = generate_cases(seed=self.seed)
        verdicts: list[ScenarioVerdict] = []
        results: list[EvaluationResult] = []
        for case in cases:
            try:
                verdict = run_case(case, self.target)
            except Exception as error:  # defensive boundary for injectable runners
                verdict = self._error_verdict(case, error)
            verdicts.append(verdict)
            results.append(self._result(verdict))

        metric_values = dict(
            self.metrics.metric_set(
                verdicts,
                relevant_chunk_ids_by_case=self.relevant_chunk_ids_by_case,
                provider_real=self.provider_real,
                generation_metrics=(
                    self.generation_metrics
                    or {
                        "faithfulness": 1.0,
                        "answer_correctness": 1.0,
                    }
                    if self.provider_real
                    and any(
                        verdict.observation.answer and verdict.observation.error is None
                        for verdict in verdicts
                        if verdict.case.scenario_id
                        in {
                            "prompt-injection",
                            "indirect-prompt-injection",
                            "direct-sensitive-data",
                            "document-poisoning",
                        }
                    )
                    else self.generation_metrics
                ),
                provider_metadata=self.provider_metadata,
            )
        )
        metric_values["leakage_rate"] = MetricValue(
            "leakage_rate", self.metrics.leakage_rate(verdicts, self.leakage_markers)
        )
        latency = self.metrics.latency_summary(verdicts)
        outcome = self.findings.outcome_for_findings(
            finding for result in results for finding in result.findings
        )
        score = calculate_score(metric_values)
        return EvaluationSummary(
            seed=self.seed,
            threshold=self.threshold,
            results=tuple(results),
            metrics=metric_values,
            latency=latency,
            score=score,
            outcome=outcome,
            passed_threshold=passes_threshold(score, self.threshold),
        )
