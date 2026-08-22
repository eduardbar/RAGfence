# Changelog

All notable changes to RAGFence are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

## [0.2.0] - 2026-08-22

### Added

- Security regression detection: `ragfence test --baseline <report.json>`
  compares per-control status against a previous run, lists regressions in
  text output, adds a `regressions` array to the JSON report, and exits 1 when
  a previously passing control or gate regresses — even if the current gate
  passes.
- Policy profiles: `ragfence test --profile {default,strict,permissive}` with
  documented threshold precedence (explicit flag > profile > config); strict
  additionally fails closed when any control is not PASS.
- Standalone HTML report viewer: `ragfence report <report.json>` renders a
  self-contained, fully HTML-escaped report (scores, outcome badge, controls,
  findings) with optional `--output` and `--open`.
- Non-gate indirect prompt injection attack scenarios: retrieved-content
  exfiltration, ACL override, hidden-chunk disclosure, metadata injection,
  and cross-session leakage — deterministic, redaction-safe, additive to the
  frozen 8-control production matrix.
- Qdrant vector store adapter (`QdrantVectorStore`) mirroring the ACL
  semantics as payload pre-filters via `build_qdrant_filter`, with in-memory
  test coverage; installable through the new `qdrant` extra.
- Vulnerable demo target (`examples/vulnerable-target/`) with the classic
  filter-after-retrieval bug, wire-contract tests, and a break-fix tutorial
  (`docs/tutorials/broken-rag.md`).
- Docker image assets: non-root `Dockerfile` and `docker-publish.yml`
  workflow publishing `ghcr.io/eduardbar/ragfence` on releases.
- First-party GitHub Action (`action.yml`) published to the GitHub
  Marketplace as RAGFence Security Evaluation.
- `SECURITY.md` vulnerability disclosure policy; README badges and sample
  evaluation graphic; PyPI-first quickstart.

### Added

- `SECURITY.md`: vulnerability disclosure policy with private reporting,
  triage timelines, scope, and safe harbor.
- First-party GitHub Action (`action.yml`, composite): provisions pgvector,
  installs `ragfence`, runs the fail-closed evaluation, uploads the JSON
  report artifact, and exposes a `gate-passed` output. Marketplace-ready via
  the `eduardbar/ragfence-action@v1` tag.
- README badges (CI, PyPI, Python versions, license, security policy) and a
  sample evaluation-report graphic; PyPI-first quickstart section.

## [0.1.0] - 2026-08-21

### Added

- Production evaluation path: declarative control matrix (8 required controls),
  fail-closed `EvaluationGate` with PASS / FAIL / INCONCLUSIVE / SKIPPED statuses,
  and security / utility / overall scores.
- ReferenceAdapter backed by PostgreSQL 16 + pgvector with DB-resolved identities:
  Acme + Globex tenants, tenant isolation enforced before vector search,
  soft-delete and clearance blocking, MUST_ALLOW / MUST_BLOCK semantics.
- Identity strategies for `generic_http`: header templates with allowlisted actor
  placeholders and bearer-token resolution from environment configuration.
- Secret redaction across reports, findings, reasons, and errors.
- Self-contained wheel: `ragfence init --up` bootstraps the bundled pgvector
  reference environment without a repository checkout.
- Idempotent bootstrap: a reachable reference database is migrated and reseeded
  in place without invoking Docker Compose.
- Reusable GitHub Actions evaluation workflow with mandatory pgvector service,
  healthchecks, real Alembic migrations, seeded data, and JSON report artifacts.

### Changed

- Reports with a `.json` destination are always machine-parseable, with or
  without `--json`.
- Explicit `--config` paths that do not exist fail closed with an actionable
  error instead of silently falling back to defaults.
- Unwritable report destinations fail closed with exit code 2 and an actionable
  message.

### Security

- Least-privilege permissions on both CI workflows.
- Dependency audit clean (`pip-audit`); no secrets in package artifacts;
  sdist excludes local agent tooling state.
