# Tasks: RAGFence Open Source Release Readiness (Phase 12)

All apply work follows RED → GREEN → REFACTOR. This artifact-only phase creates no production changes, tests, docs, commits, pushes, or deploys.

## 1. Contract checkpoint and inventory

- [x] 1.1 RED: create a release matrix mapping every Phase 12 deliverable and spec scenario to an exact file, command, offline assertion, Docker check, benchmark, audit, or public-CI receipt; run it and observe missing release evidence.
- [x] 1.2 GREEN: freeze canonical names, supported versions, CLI commands/options, report schema/path, exit codes 0/1/2, example paths, DB prerequisites, and the v0.1 performance budget/baseline.
- [x] 1.3 REFACTOR: review the matrix against all six `docs/*.md`, README, CONTRIBUTING, `pyproject.toml`, both workflows, and archived Phase 0–11 contracts; confirm only release-readiness-owned files are in scope.

## 2. Full docs and contributor pass (TDD)

- [x] 2.1 RED: add offline consistency/link/path tests and README quickstart tests; run them and capture contradictions or missing links.
- [x] 2.2 GREEN: align docs and README quickstart, report semantics, Docker/offline boundaries, examples, and canonical names; add `CODE_OF_CONDUCT.md` and `CHANGELOG.md` with release-safe contact/version policy.
- [x] 2.3 REFACTOR: run the full docs checker, markdown/link checks, and command-snippet validation without network or credentials; remove unsupported promises and stale Phase 0 status.

## 3. Packaging and wheel smoke

- [x] 3.1 RED: add a packaging test that builds/inspects a wheel and runs it from a fresh non-editable venv; verify it fails until the release contract is satisfied.
- [x] 3.2 GREEN: make the smallest packaging/docs/package-data corrections needed for `uv build`, wheel-only install, import, `ragfence --help`, and documented smoke execution.
- [x] 3.3 REFACTOR: repeat smoke from a cwd/PYTHONPATH that cannot import the checkout; inspect wheel contents and assert no secrets/unintended files.

## 4. Examples and generic HTTP stub

- [x] 4.1 RED: add offline config-validation tests for reference and `[adapters.generic_http]` examples, including secret-shaped values, URL/path, timeout, and retry rules; add stub contract tests and observe failure.
- [x] 4.2 GREEN: add copyable non-secret example configs and the minimal deterministic local stub; prove adapter check, happy-path evaluation, malformed/non-JSON response, timeout, and fail-closed behavior.
- [x] 4.3 REFACTOR: run the complete example/stub suite with network disabled; inspect logs/reports for credentials, unrestricted content, and unstable output.

## 5. Clean E2E and Docker database proof

- [x] 5.1 RED: add offline preflight/CLI command-double tests for ordered `init → seed → test → report`, report schema/non-empty checks, fake providers, and statuses 0/1/2; add DB-marked tests for migration, seed idempotency, Acme traps, and tenant isolation.
- [x] 5.2 GREEN: wire only release-proof fixtures/scripts/configuration needed to execute offline E2E and Docker PostgreSQL 16 + pgvector E2E in a disposable environment.
- [x] 5.3 REFACTOR: run offline tests with Docker absent (record explicit DB skips), then run the Docker suite from a clean database; capture exact outputs and verify no external keys/network are needed.

## 6. Acme performance sanity

- [x] 6.1 RED: add a deterministic benchmark assertion/report schema for embedding setup, steady-state search p50/p95, corpus/query counts, errors, and leakage/authorization invariants; run it against the unfrozen budget and observe failure.
- [x] 6.2 GREEN: freeze the documented v0.1 budget or reviewed baseline and make the benchmark pass without external providers or unbounded load.
- [x] 6.3 REFACTOR: repeat benchmark under the declared environment, compare runs, and record reproducible evidence without claiming unsupported production capacity.

## 7. CI and public-main gate

- [x] 7.1 RED: add offline YAML structure/security tests for both workflows, ordered quality/evaluation steps, fake-provider defaults, artifacts/summary/final gate, and no-secret logging; verify they catch removed/misordered gates.
- [x] 7.2 GREEN: make only release-contract corrections required to preserve baseline CI and reusable evaluation workflow behavior; do not add live GitHub calls to tests.
- [ ] 7.3 REFACTOR: run offline workflow tests locally, then inspect the public `main` run for the release commit and record URL, SHA, check names, and green status; never infer this receipt from local output.

## 8. Dependency and secret audit

- [x] 8.1 RED: add an audit harness that scans the lockfile/wheel environment, tracked files, generated artifacts, and reachable history; run it and enumerate findings.
- [x] 8.2 GREEN: resolve or explicitly block on vulnerabilities/secrets; run `uv audit` or documented `pip-audit` fallback and secret scanners with `.env.example` placeholder policy.
- [x] 8.3 REFACTOR: rerun audits from a clean environment, verify logs/reports redact DSNs/tokens/provider payloads, and record tool versions, scopes, findings, waivers, and owner.

## 9. Final verification and handoff

- [x] 9.1 RED: assemble a release checklist command that fails when any matrix item lacks evidence, including Docker skips or missing public-CI receipt.
- [ ] 9.2 GREEN: satisfy all applicable offline, wheel, Docker, benchmark, audit, and public-CI evidence gates with exact command output.
- [x] 9.3 REFACTOR: run the complete release verification, classify intentional skips/blockers, and ensure evidence is reproducible and secret-free.
- [ ] 9.4 Review: verify this artifact phase changed exactly the four files under `openspec/changes/ragfence-release-readiness/`; leave implementation, commits, pushes, publication, and deploys to later phases.
