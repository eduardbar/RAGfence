# Tasks: RAGFence Evaluation / Reporting (Phase 8)

Tasks are strict RED → GREEN → REFACTOR. Paths are exact. Tasks in the same work unit may run in parallel after their listed dependencies; integration dependencies are explicit.

## Work Unit A — Contracts, metrics, and scoring

- [x] A1 RED: add `tests/test_evaluation_contracts.py` covering suite summary/result contracts, metric names, score type, and threshold type; depends on Phase 7 contracts.
- [x] A2 GREEN: create `src/ragfence/evaluation/contracts.py` with typed in-memory suite/run/result/report contracts that wrap `ScenarioVerdict` and `ScenarioObservation` without changing them; depends on A1.
- [x] A3 REFACTOR: run focused contract tests and remove duplicate representations while preserving Phase 7 imports; depends on A2.
- [x] A4 RED: add `tests/test_evaluation_metrics.py` for context precision/recall, faithfulness/correctness evidence handling, leakage rate, unauthorized-retrieval rate, latency, and optional cost; depends on A2.
- [x] A5 GREEN: create `src/ragfence/evaluation/metrics.py` with deterministic bounded metric functions and explicit unavailable-data policy; depends on A4.
- [x] A6 RED: add `tests/test_evaluation_scoring.py` for 0, 100, clamping, weighted aggregation, rounding, and threshold equality; depends on A5.
- [x] A7 GREEN: create `src/ragfence/evaluation/scoring.py` with frozen 0–100 weights, normalization, clamp, and `score >= threshold`; depends on A6.
- [x] A8 REFACTOR: run A tests plus existing Phase 7 tests and document the canonical 0–100 scale in module docstrings; depends on A7.

## Work Unit B — Findings and redaction

- [x] B1 RED: add `tests/test_evaluation_findings.py` covering leakage, unauthorized retrieval, target errors, clean cases, and LOW/MEDIUM/HIGH/CRITICAL outcome mapping; depends on Phase 7 and A2.
- [x] B2 GREEN: create `src/ragfence/evaluation/findings.py` for finding creation, category policy, severity mapping, and `ScenarioOutcome` derivation; depends on B1.
- [x] B3 RED: add `tests/test_evaluation_redaction.py` proving bearer/API-key/authorization/chunk-content redaction, marker removal, bounded errors, and stable safe IDs/hashes; depends on B2.
- [x] B4 GREEN: create `src/ragfence/evaluation/redaction.py` with recursive redaction and deterministic truncation used by findings and reports; depends on B3.
- [x] B5 REFACTOR: consolidate the existing CLI redaction behavior behind the shared safe representation without changing current `tests/test_cli_reporting.py`; depends on B4.

## Work Unit C — Repositories

- [x] C1 RED: add `tests/test_evaluation_repositories.py` with repository contract tests for suite/case/run/result/finding writes, reads, links, and replay idempotency; depends on A2 and B4.
- [x] C2 GREEN: create `src/ragfence/evaluation/repositories.py` with repository protocols and SQLAlchemy implementation against the exact five existing ORM models in `src/ragfence/db/models.py`; depends on C1.
- [x] C3 RED: add DB-gated tests for stable UUID/case replay and finding reconciliation using existing Alembic schema; depends on C2.
- [x] C4 GREEN: implement transaction-safe upsert/reconcile semantics without adding tables or migrations; depends on C3.
- [x] C5 REFACTOR: run repository contract tests and verify all foreign keys, enum values, decimal score precision, and redacted JSONB payloads; depends on C4.

## Work Unit D — In-memory EvaluationEngine

- [x] D1 RED: add `tests/test_evaluation_engine.py` for all generated cases, continued execution after one error, verdict-to-result mapping, metrics, findings, score, outcome, and threshold status; depends on A8 and B5.
- [x] D2 GREEN: create `src/ragfence/evaluation/engine.py` orchestrating `scenario_catalog`, `generate_cases`, `run_case`, A contracts/metrics/scoring, and B findings/redaction in memory; depends on D1.
- [x] D3 RED: add determinism tests proving same seed/observations produce byte-equivalent engine summaries; depends on D2.
- [x] D4 GREEN: make engine ordering, fingerprints, rounding, and missing-evidence behavior deterministic; depends on D3.
- [x] D5 REFACTOR: run engine tests with no DB/network/API keys and preserve the Phase 7 handoff; depends on D4.

## Work Unit E — Report artifact

- [x] E1 RED: add `tests/test_evaluation_report.py` for canonical JSON ordering, stable case/finding ordering, 0–100 fields, threshold fields, and injected/omitted timestamps; depends on B4 and D2.
- [x] E2 GREEN: create `src/ragfence/evaluation/report.py` producing the canonical report artifact and text projection; depends on E1.
- [x] E3 RED: extend `tests/test_cli_reporting.py` only with compatibility assertions for the new payload fields and redaction; depends on E2.
- [x] E4 GREEN: adapt `src/ragfence/cli/reporting.py` through the report seam without breaking the existing `EvaluationReport` constructor/render tests; depends on E3.
- [x] E5 REFACTOR: run report and CLI reporting suites and verify identical canonical bytes across repeated renders; depends on E4.

## Work Unit F — CLI integration

- [x] F1 RED: add `tests/test_evaluation_cli_seam.py` for explicit legacy 0–1 to 0–100 conversion, native engine threshold, exit codes 0/1/2, JSON write, and invalid config; depends on D5 and E5.
- [x] F2 GREEN: adapt `src/ragfence/cli/config.py`, `src/ragfence/cli/seams.py`, and `src/ragfence/cli/main.py` only at the boundary so existing 0–1 tests remain valid and Phase 8 receives 0–100; depends on F1.
- [x] F3 REFACTOR: run the complete existing CLI test suite plus focused seam tests; do not migrate the public config scale in this change; depends on F2.

## Work Unit G — DB-gated end-to-end

- [x] G1 RED: add `tests/test_evaluation_e2e_db.py` (DB marker) asserting a full generated suite populates all five tables and round-trips score/outcome/redacted evidence; depends on C5, D5, and F3.
- [x] G2 GREEN: wire `EvaluationEngine` persistence through repositories and ensure transaction rollback on failed runs; depends on G1.
- [x] G3 RED: add replay tests for identical suite/case/observation inputs and report-byte equality after reload; depends on G2.
- [x] G4 GREEN: complete idempotent replay/reconciliation and DB-gated CLI artifact path; depends on G3.
- [x] G5 REFACTOR: run DB-gated tests against the existing Alembic schema, then run the full non-DB suite, lint, typecheck, and formatting checks; depends on G4.

## Verification and Handoff

- [x] V1: verify only the four files in this OpenSpec change are created before implementation begins; no production implementation, commit, or push is part of this artifact task.
- [x] V2: after implementation, require focused RED evidence, GREEN evidence, REFACTOR evidence, and the DB-gated result before marking Phase 8 complete.
