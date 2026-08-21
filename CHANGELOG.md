# Changelog

All notable changes to RAGFence are documented here. This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.

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
