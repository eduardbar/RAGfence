# Design: RAGFence Open Source Release Readiness

## Release contract

Phase 12 is a proof layer over existing contracts, not a feature layer. The release checklist should map every claim to one of: an offline parser/static test, a clean-venv command, a Docker-backed PostgreSQL/pgvector test, a local HTTP stub test, a benchmark result, a dependency/security scan, or a live public-CI receipt. No local green result is presented as proof of public GitHub CI.

## Documentation and public UX

Create a docs consistency matrix keyed by canonical names from `TRD.md`: CLI commands/options, package/version/Python support, adapters, report fields and exit codes, configuration keys, database prerequisites, synthetic Acme fixtures, security boundaries, and out-of-scope items. Check every claim in PRD, TRD, APP_FLOW, UI/UX, BACKEND_SCHEMA, IMPLEMENTATION_PLAN, README, and CONTRIBUTING. The README becomes the shortest runnable path: prerequisites, isolated install, `ragfence --help`, `ragfence init`, seed/reference mode, `ragfence test`, report location, exit-code interpretation, and `generic_http` usage. Links point to contribution rules, Code of Conduct, changelog, and the complete docs map.

The contribution package consists of `CONTRIBUTING.md`, a root `CODE_OF_CONDUCT.md` using a recognized inclusive standard with project reporting contact, and `CHANGELOG.md` with the current release/unreleased policy. These artifacts must not promise unsupported features or require secrets.

## Packaging and installation smoke

Build into a disposable output directory with `uv build`. Create a fresh venv outside the repository, install only the produced wheel (and only documented runtime dependencies), verify metadata/import/console entry point, and run `ragfence --help`. The smoke must not accidentally import the checkout (`cwd`, `PYTHONPATH`, and editable-install remnants are excluded). Validate wheel contents for required package data and absence of source secrets. Keep build output disposable and outside the change artifacts.

## Examples and generic HTTP stub

Use checked-in, non-secret example files (for example `examples/ragfence.reference.toml` and `examples/ragfence.generic_http.toml`) whose keys match the configuration schema in `TRD.md` and the Phase 9 adapter contract. Values are localhost/placeholders; bearer values are environment references or clearly fake placeholders and are never printed. A minimal local stub exposes health, retrieval, and optional answer responses matching strict adapter wire models, returns deterministic synthetic chunks, and supports malformed/timeout fixtures for offline tests. The example path proves `adapter check` and `test --adapter generic_http` without external network access.

## E2E and database boundary

The offline suite covers docs/config parsing, wheel metadata, CLI help, example validation, report schema/redaction, stub HTTP behavior, workflow YAML ordering, and secret scanning with doubles; it never calls GitHub, PyPI, model providers, or an external target. The DB suite is marked/selected explicitly and runs against disposable PostgreSQL 16 + pgvector via Docker: initialize, migrate, seed Acme deterministically, run the reference evaluation, and assert a non-empty report, expected trap outcomes, tenant isolation, and idempotent reseeding. A clean-environment script records `init → seed → test → report` and exit statuses 0/1/2.

## Performance sanity

Benchmark the deterministic Acme corpus using the public embedding and search seams, separating cold setup from steady-state operations and recording environment, corpus size, query count, p50/p95 latency, and errors. The release gate compares the result with the v0.1 budget frozen from the canonical docs; if the docs lack a numeric budget, the apply phase must freeze a reviewable baseline before GREEN rather than inventing a claim. Performance evidence must also assert zero unauthorized retrieval/leakage and no network/provider dependency.

## CI and security gates

Parse `.github/workflows/ci.yml` and `ragfence-test.yml` offline to ensure install, lint, format, type, test, init/readiness, evaluation, artifact, summary, fake-provider, and final-gate contracts remain intact. The live public-main gate is a manual/release verification input: capture the GitHub run URL/commit/status and do not fabricate it locally. Run the lockfile/package audit (`uv audit` where supported, otherwise `pip-audit` against the built environment), plus secret scanners over tracked files and history. Classify findings as release-blocking unless explicitly waived with owner and rationale. Do not expose DSNs, tokens, headers, provider payloads, or environment dumps in logs/reports.

## TDD verification sequence

Each implementation slice follows RED (focused test fails for the missing release contract), GREEN (smallest docs/config/test/tooling change), REFACTOR (full relevant offline or Docker gate). Verification records exact commands, environment, skips, benchmark values, audit findings, and the public CI receipt; artifact authoring itself creates only this OpenSpec change.
