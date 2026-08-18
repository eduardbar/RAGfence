# Tasks: RAGFence CI Integration (Phase 11)

All implementation work follows RED → GREEN → REFACTOR. The tasks below describe the later apply phase; this artifact-only change does not implement production code, workflow YAML, tests, commits, or pushes.

## 1. Contract checkpoint

- [x] 1.1 RED: add a contract-test inventory mapping each Phase 11 requirement to an offline assertion and the Phase 8/9/CLI source contract.
- [x] 1.2 GREEN: freeze workflow inputs (`adapter`, `target`, `base-url`, `threshold`, startup command, comment flag, fake-provider flag), report path, artifact name, and exit-status handoff.
- [x] 1.3 REFACTOR: review the inventory against `docs/IMPLEMENTATION_PLAN.md` Phase 11 and `docs/APP_FLOW.md`; confirm `.github/workflows/ci.yml` remains outside the change.

## 2. Offline workflow structure tests (TDD first)

- [x] 2.1 RED: create `tests/test_ci_workflow_structure.py` with a local YAML loader and assertions for `workflow_call`, required inputs/defaults, Python 3.12 matrix, and least-privilege permissions; run it and observe failure because `ragfence-test.yml` is not yet present.
- [x] 2.2 GREEN: create `.github/workflows/ragfence-test.yml` with checkout, setup-python, install, and the reusable input contract until the structure tests pass.
- [x] 2.3 RED: add an ordered-step assertion for `ragfence init --up`, target startup/readiness, adapter/base URL/threshold arguments, JSON output, and the fixed report path.
- [x] 2.4 GREEN: implement the ordered workflow steps and bounded readiness handling; no production CLI or adapter changes.
- [x] 2.5 REFACTOR: make assertions parser-based and resilient to harmless YAML formatting while rejecting reordered/missing required steps.

## 3. Exit, artifact, and summary behavior

- [x] 3.1 RED: add local command-double tests for CLI statuses 0, 1, and 2, asserting artifact/summary execution and final status propagation; include a missing-report case.
- [x] 3.2 GREEN: capture the evaluation status without swallowing it, upload JSON under `if: always()`, render `$GITHUB_STEP_SUMMARY`, and re-emit the captured status in a final gate.
- [x] 3.3 RED: add a fixture test proving a below-threshold report remains uploadable and the final gate is still exit 1.
- [x] 3.4 GREEN: wire report-path validation and status handling so no missing/empty success report can pass.
- [x] 3.5 REFACTOR: run focused offline tests and verify the summary distinguishes threshold failure from configuration/runtime error.

## 4. Determinism and fake-provider guard

- [x] 4.1 RED: add tests that inspect explicit fake embedding/LLM defaults and compare two equivalent fixture reports after removing timestamps/run IDs.
- [x] 4.2 GREEN: set the documented fake-provider environment/configuration explicitly and add a deterministic report comparison guard.
- [x] 4.3 RED: add a negative test where a provider secret or timestamp is included in a report/log path and assert it is rejected or excluded.
- [x] 4.4 GREEN: enforce canonical stable fields, bounded report rendering, and no required external provider credentials.
- [x] 4.5 REFACTOR: confirm determinism tests use only local fixtures and do not call HTTP, GitHub, Docker registries, or model providers.

## 5. PR summary/comment safety

- [x] 5.1 RED: add tests for fork PR, same-repository PR, comments disabled, and repeated-run marker behavior.
- [x] 5.2 GREEN: add the trusted same-repository guard, conditional least-privilege write permission, and marker-idempotent comment update; always retain summary/artifact behavior for forks.
- [x] 5.3 RED: add static safety assertions rejecting `eval`, environment dumps, unmasked secret interpolation, full report/provider payload logging, and unsafe shell interpolation.
- [x] 5.4 GREEN: render only bounded, redacted scalar report fields through safe environment-file/script interfaces.
- [x] 5.5 REFACTOR: run the full offline workflow-structure/security test group without GitHub credentials or network access.

## 6. Verification and handoff

- [x] 6.1 RED: add a local test that parses the final workflow and reports every required step/condition by name, including artifact and final gate.
- [x] 6.2 GREEN: satisfy the full offline contract suite and document the exact local command used to run it.
- [x] 6.3 REFACTOR: run repository YAML/config linting plus the focused tests; do not claim a live GitHub manual PR result from local execution.
- [x] 6.4 Review: verify no files outside `openspec/changes/ragfence-ci-integration/` are modified during this artifact phase; leave implementation and commits to the apply phase.
