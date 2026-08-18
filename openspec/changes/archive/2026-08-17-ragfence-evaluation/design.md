# Design: RAGFence Evaluation / Reporting

## Technical Approach

Keep Phase 7 as the execution boundary. The engine receives deterministic cases and `ScenarioVerdict` values (whose `ScenarioObservation` contains retrieved chunks, answer, error, and latency), derives normalized metrics and findings, computes one frozen 0–100 score, and emits a report plus persistence commands. Pure contracts, metrics, scoring, finding construction, redaction, and report serialization remain usable without PostgreSQL; repositories and the end-to-end path are explicitly DB-gated.

## Work Units and Parallelization

| Work unit | Owns | Depends on | Parallelism |
|---|---|---|---|
| A. Contracts / metrics / scoring | Evaluation summary value objects, metric functions, score weights, 0–100 boundaries, threshold predicate | Phase 7 contracts and existing enums | Parallel with B, C, E |
| B. Findings / redaction | Severity/category mapping, evidence builder, secret/chunk redaction and truncation | Phase 7 observation/verdict shapes; A for score context only | Parallel with A, C, E |
| C. Repositories | Five-table repository interfaces and SQLAlchemy implementation, stable upsert/idempotency keys | Existing `src/ragfence/db/models.py` and migrations | Parallel with A, B, E |
| D. Engine in-memory | Suite orchestration, verdict-to-result mapping, findings, metrics, scoring, outcome | A + B; consumes Phase 7 | Starts after A/B contracts; independent of C/E |
| E. Report artifact | Canonical payload, injected metadata/timestamp policy, JSON/text rendering and writer seam | A + B; existing `cli/reporting.py` | Parallel with A/B/C; integrate after D |
| F. CLI integration | Legacy threshold adapter, engine invocation seam, exit code 0/1/2, report destination | D + E; existing `cli/config.py` and `cli/main.py` | After D/E; preserves current tests |
| G. DB-gated end-to-end | PostgreSQL repository wiring, five-table round trip, replay/idempotency and full CLI path | C + D + E + F; Alembic schema available | Final gated work unit |

Each work unit follows RED → GREEN → REFACTOR and can be developed in separate branches/worktrees before a final integration pass. No work unit may modify Phase 7 behavior.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| ADR-1 | Execution input | `EvaluationCase` + `ScenarioVerdict` from `run_case` | Reuses the stable Phase 7 seam and keeps scenario definitions declarative. |
| ADR-2 | Score scale | Inclusive 0–100, clamped, threshold equality passes | Matches Phase 8/PRD output (`82/100`) and makes CI gating unambiguous. |
| ADR-3 | Scoring | Weighted mean of normalized metrics, with security metrics included and deterministic missing-metric policy | Supports retrieval/generation/security/operations while avoiding hidden judge calls. |
| ADR-4 | Outcome | Highest applicable finding severity, with clean cases PASS and non-security incomplete/unsupported evidence WARNING | Separates score from actionable security severity and uses existing enums. |
| ADR-5 | Security truth | Any unauthorized retrieved chunk or sensitive marker in answer is a leakage/security finding | Retrieval-before-generation is the product security boundary; post-hoc answer filtering cannot erase retrieval exposure. |
| ADR-6 | Evidence | Store IDs, hashes, bounded metadata, verdict reason, and redacted snippets only | `security_findings.evidence` is JSONB and must be reproducible without persisting secrets. |
| ADR-7 | Persistence | Stable UUIDs/fingerprints and upsert/reconcile semantics | Re-runs must be safe and queryable across the existing five tables. |
| ADR-8 | Report determinism | Canonical sorted JSON; generated time is injected/omitted from the deterministic payload | Same inputs produce byte-identical reports; wall-clock values do not cause false diffs. |
| ADR-9 | CLI migration | Keep current 0–1 `CliConfig` contract, translate explicitly at the seam to 0–100 | Existing Phase 6 tests must not break before the future CLI migration. |

## Metrics and Scoring Contract

- Retrieval: context precision is relevant retrieved chunks / retrieved chunks; context recall is relevant retrieved chunks / expected relevant chunks. When fixture ground truth is unavailable, the metric is marked unavailable rather than guessed.
- Generation: faithfulness and answer correctness are deterministic evidence-based values; absent generation evidence yields a documented neutral/unsupported policy and a WARNING where applicable.
- Security: leakage rate = leaked cases / cases; unauthorized-retrieval rate = cases with unauthorized retrieved chunks / cases. Zero is the secure target.
- Operations: latency is retained as a distribution/summary; cost is retained only when supplied, never fabricated.
- Metric-to-score normalization is explicit and bounded; security rates are inverted (`1 - rate`). The implementation must expose weights and document the missing-metric policy in the report. Final score is rounded deterministically to two decimals and clamped to [0, 100].

## Outcome Mapping

`CRITICAL` finding → `ScenarioOutcome.CRITICAL`; otherwise `HIGH` → `FAIL`; otherwise `MEDIUM` or unsupported/incomplete evaluation evidence → `WARNING`; no findings → `PASS`. A threshold failure by itself does not invent a security finding: the report keeps the derived outcome and separately exposes `passed_threshold=false`.

## Persistence Shape

- `evaluation_suites`: stable suite name/configuration and canonical 0–100 threshold at the engine boundary (legacy conversion happens before persistence).
- `evaluation_cases`: one row per stable Phase 7 case, actor JSON snapshot, prompt, expected allow.
- `evaluation_runs`: status, score, threshold, `ScenarioOutcome`, timestamps, and one run fingerprint.
- `evaluation_results`: one row per run/case with passed/outcome, chunk IDs, answer, latency.
- `security_findings`: case/run/result links, enum severity, category, title/description, redacted evidence.

The repository layer must respect existing ORM columns and migrations; if a fingerprint is not a schema column, derive idempotency by querying the stable suite/case/run inputs rather than adding a table or migration in this change.

## CLI Seam

The engine-facing CLI seam accepts canonical 0–100 threshold values. Until migration, `load_config` continues validating legacy 0–1 values and the command converts them once, explicitly, before calling the engine. `--threshold` follows the existing compatibility contract in this change; invalid ranges remain configuration errors (exit 2), below-threshold is exit 1, and passing is exit 0. JSON output uses sorted keys and the existing redaction path.

## File/Module Targets (Implementation Guidance)

- `src/ragfence/evaluation/contracts.py`, `metrics.py`, `scoring.py`: work unit A.
- `src/ragfence/evaluation/findings.py`, `redaction.py`: work unit B.
- `src/ragfence/evaluation/repositories.py` and DB repository implementation: work unit C.
- `src/ragfence/evaluation/engine.py`: work unit D.
- `src/ragfence/evaluation/report.py` plus compatibility wiring to `src/ragfence/cli/reporting.py`: work unit E.
- `src/ragfence/cli/seams.py`, `src/ragfence/cli/config.py`, and `src/ragfence/cli/main.py`: work unit F, only where tests prove the seam requires it.
- `tests/` additions mirror each unit; DB tests are marked/gated and require the existing Alembic/PostgreSQL setup.
