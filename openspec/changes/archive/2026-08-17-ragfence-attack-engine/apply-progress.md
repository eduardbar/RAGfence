# Apply Progress: RAGFence Attack Engine (Phase 7)

## Work Unit 1 — Scenario Catalog

- RED: added tests for the ten canonical PRD IDs, order, target stages, and expected behavior.
- GREEN: implemented the immutable declarative catalog in `src/ragfence/attacks/scenarios.py` and exported it publicly.
- REFACTOR: catalog tests and attack-module typing/lint gates passed.

## Work Unit 2 — Deterministic Generators

- RED: added same-seed serialization, UUID5, synthetic actor, expected behavior, top_k, and arbitrary-filter tests.
- GREEN: implemented Acme-backed `EvaluationCase` generation, bounded top_k, and filter validation.
- REFACTOR: generator tests and the full non-DB suite passed.

## Work Unit 3 — Runner and Verdicts

- RED: added no-retrieval pass, unexpected retrieval fail, and target-error containment tests.
- RED correction pass: added generation-answer oracle, real `RetrievalService` request-shape, actor-specific cases, output-limit, filter-validation, and answer-error evidence tests.
- GREEN: implemented typed observations/verdicts, stage-aware answer oracle, typed document filters, bounded output, actor/target metadata, and preserved chunks on answer errors.
- REFACTOR: public exports, focused tests, full suite, and full quality gates passed.

## Verification evidence

- `uv run pytest -q`: 203 passed, 14 skipped (database unavailable; DB-gated tests).
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run mypy`: passed, 45 source files.
- `uv build`: passed; wheel and source distribution created.

## Phase 8 handoff

The runner is pure/in-memory at the boundary and returns `ScenarioObservation` and `ScenarioVerdict`. Phase 8 owns score aggregation, severity mapping, persistence, and CLI evaluation integration.
