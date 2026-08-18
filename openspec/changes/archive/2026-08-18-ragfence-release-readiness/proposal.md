# Proposal: RAGFence Open Source Release Readiness (Phase 12)

## Intent

Turn the completed Phase 0–11 product contracts into a verifiable, publishable open-source release contract. This change is release hardening only: it aligns the public documentation and contributor experience, proves installation and the documented end-to-end path, validates the reference and `generic_http` examples, checks Acme performance, and establishes security/CI release gates.

## Scope

- Perform a full consistency pass across `docs/PRD.md`, `TRD.md`, `APP_FLOW.md`, `UI_UX_DESIGN_BRIEF.md`, `BACKEND_SCHEMA.md`, and `IMPLEMENTATION_PLAN.md`.
- Make the README quickstart executable from a clean environment, including reference and external-target paths, expected report/exit semantics, and links to contribution, conduct, changelog, and docs.
- Provide the public contribution guide, Code of Conduct, and changelog required for release.
- Prove `uv build`/wheel installation in a fresh isolated environment and run `ragfence --help` plus the documented smoke path from the installed wheel.
- Specify non-secret example configurations for the reference target and `[adapters.generic_http]`, plus a minimal local generic HTTP stub project/fixture.
- Run an Acme Corp performance sanity check for deterministic embedding and authorized search against the documented v0.1 budget.
- Verify both CI workflows locally/offline and record public `main` CI evidence separately when a live GitHub check is available.
- Verify clean-environment E2E `init → seed → test → report`, using Docker PostgreSQL/pgvector only for database-gated checks and offline doubles for all other checks.
- Audit dependencies and repository/history for known vulnerabilities and secrets; `.env.example` and examples contain placeholders only.

## Dependencies and contracts

- Phases 0–11 and their CLI, adapter, evaluation, report, database, fake-provider, and CI contracts.
- `pyproject.toml` package metadata, `ragfence` console entry point, Python >= 3.12, and the existing lockfile/tooling gates.
- `docs/APP_FLOW.md` quickstart/CI/adapter journeys and `docs/TRD.md` configuration, provider, redaction, and performance contracts.
- Existing `.github/workflows/ci.yml` remains the baseline quality workflow; `ragfence-test.yml` remains the evaluation workflow.

## Success criteria

1. Documentation names, commands, paths, status/exit semantics, and supported boundaries agree across all referenced docs.
2. A clean venv can install the built wheel and execute the README smoke commands without API keys.
3. Example reference and `generic_http` configurations are copyable, valid, bounded, and secret-free; the stub supports the documented adapter check/evaluation path.
4. Clean E2E produces a non-empty, schema-valid report; pass, below-threshold, and configuration-error exit semantics remain 0/1/2.
5. Acme embedding/search measurements are captured and within the explicitly frozen v0.1 budget, with no unauthorized retrieval/leakage.
6. Offline tests prove both workflow structures and no-secret policy; Docker tests prove DB/migration/E2E behavior where required.
7. Dependency/security audit is clean or has explicitly documented, release-blocking findings; no secret is present in tracked files, examples, artifacts, or history.
8. Public `main` CI is green, evidenced by a live check URL/run identifier rather than inferred from local execution.

## Out of scope

- New product features, schema/model behavior, adapters beyond `generic_http`, or changes to production semantics.
- Modifying workflows, source, tests, docs, packaging metadata, or repository history in this artifact-authoring phase; those belong to apply tasks.
- Commits, tags, pushes, PyPI publication, deploys, or branch-protection administration.
- Real provider credentials, live external RAG targets, unbounded load testing, or non-synthetic data.
