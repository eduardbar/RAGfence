# Proposal: RAGFence Evaluation / Reporting (Phase 8)

## Intent

Implement the Phase 8 evaluation and reporting layer described by `docs/IMPLEMENTATION_PLAN.md`, consuming the existing Phase 7 contracts (`scenario_catalog`, `generate_cases`, `run_case`, `ScenarioObservation`, and `ScenarioVerdict`). The result is a deterministic `EvaluationEngine` that turns cases and verdicts into metrics, findings, outcomes, a persisted run, and a JSON report without changing the Phase 7 runner contract.

## Scope

### In Scope

- `EvaluationEngine` orchestration from generated cases through observations/verdicts, per-case results, findings, suite/run summaries, and report artifacts.
- Retrieval metrics: context precision and recall; security metrics: leakage rate and unauthorized-retrieval rate; generation metrics: faithfulness and answer correctness when answer evidence is available; operational metrics: latency and cost when supplied by the adapter/evidence.
- Findings and outcome derivation using the existing `FindingSeverity` and `ScenarioOutcome` enums.
- A frozen score scale of **0–100 inclusive**, weighted and deterministic, with explicit score-boundary and threshold semantics.
- Persistence of the five existing evaluation tables, unchanged in shape: `evaluation_suites`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, and `security_findings`.
- Evidence redaction/truncation before JSONB persistence or report output; no raw authorization headers, secrets, or unrestricted chunk content in public evidence.
- Stable JSON report rendering compatible with the existing `EvaluationReport`, `render_json`, `render_text`, and report writer seam.
- A CLI integration seam that lets the current Phase 6 command call the engine and enforce a threshold.

### Out of Scope

- Production retrieval, adapter, scenario, or `ScenarioObservation`/`ScenarioVerdict` behavior changes.
- New database tables or migrations; existing Alembic-owned schema and ORM models are the persistence contract.
- Real LLM providers or probabilistic judge behavior; generation metrics remain deterministic and evidence-driven.
- CI workflow changes, generic HTTP adapter implementation, or implementation of the Phase 9/10 plan.

## Compatibility and Scale Freeze

The canonical Phase 8 score and threshold are integers/floats on **0–100**, inclusive. A run passes its configured threshold when `score >= threshold`; equality is passing. Scores must be clamped to the boundary and never emit values below 0 or above 100.

`src/ragfence/cli/config.py` currently exposes a **0–1** threshold and existing tests depend on that contract. Phase 8 MUST preserve that seam during migration: the engine-facing value is canonical 0–100, while the current CLI/config adapter may translate the legacy 0–1 value at the boundary (for example, `0.8 → 80`) without changing existing tests. The future CLI migration to native 0–100 is explicitly deferred; no implementation may silently reinterpret an existing 0–1 config as 0–100.

## Persistence Contract

A run must be queryable across all five existing tables. Stable case IDs from Phase 7 are the idempotency key for `evaluation_cases`; a stable suite identity plus run input fingerprint is the idempotency key for a rerun. Replaying the same suite/cases/observations must not duplicate cases or findings and must produce the same report payload.

## Success Criteria

- A full in-memory evaluation consumes all ten generated Phase 7 cases without importing database code.
- Boundary, mapping, unauthorized retrieval/leakage, redaction, report determinism, threshold, and idempotent persistence tests are specified and pass once implemented.
- A DB-gated end-to-end run populates all five existing tables with coherent foreign keys, redacted evidence, and a score/outcome that can be queried.
- Existing Phase 6 CLI tests remain green while the legacy 0–1 threshold seam is adapted behind an explicit compatibility boundary.
