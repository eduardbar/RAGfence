# Tasks: RAGFence Attack Engine (Phase 7)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~500 |
| 400-line budget risk | High |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | stacked-to-main |

## Phase 1: Scenario Catalog

- [x] 1.1 RED: add catalog tests for ten unique PRD IDs, order, target stages, and expected behaviors.
- [x] 1.2 GREEN: create `src/ragfence/attacks/scenarios.py` with the ten declarative `AttackScenario` definitions.
- [x] 1.3 GREEN: update `src/ragfence/attacks/__init__.py` with the public catalog export.
- [x] 1.4 REFACTOR: run catalog tests and freeze IDs as the Phase 8 persistence contract.

## Phase 2: Deterministic Generators

- [x] 2.1 RED: add generator tests for same-seed byte equality, stable UUID5 case IDs, valid actors, and expected behavior mapping.
- [x] 2.2 GREEN: create `src/ragfence/attacks/generators.py` using `build_acme_corp` and synthetic `context_for` actors.
- [x] 2.3 RED: add filter-bypass bounds tests for top_k and arbitrary filter rejection.
- [x] 2.4 GREEN: implement bounded explicit adversarial inputs for filter-bypass cases.
- [x] 2.5 REFACTOR: run generator tests and full non-DB suite.

## Phase 3: Runner and Verdicts

- [x] 3.1 RED: add runner tests for normal observations, no-retrieval block passes, unexpected retrieval failures, and target-error containment.
- [x] 3.2 GREEN: create `src/ragfence/attacks/runner.py` with typed observations, verdicts, and an injected target seam.
- [x] 3.3 RED: add tests proving scenario definitions do not perform I/O and runner latency/error fields are bounded and typed.
- [x] 3.4 GREEN: complete objective verdict logic and bounded execution handling.
- [x] 3.5 REFACTOR: run all attack-engine tests and confirm Phase 8 handoff remains pure/in-memory.

## Phase 4: Verification and Handoff

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and `uv build`.
- [x] 4.2 Record RED → GREEN evidence in `apply-progress.md`.
- [x] 4.3 Run `gentle-ai sdd-status ragfence-attack-engine` and complete native review/verification.
- [x] 4.4 Document the Phase 8 evaluation-engine integration contract.
