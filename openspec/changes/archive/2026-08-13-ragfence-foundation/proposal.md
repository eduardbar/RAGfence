# Proposal: RAGFence Foundation (Phases 0-2)

## Intent

First installable slice of RAGFence: packaging contract, canonical domain models, the deny-by-default policy decision flow, and the PostgreSQL/pgvector schema foundation (IMPLEMENTATION_PLAN Phases 0-2). Later phases (attacks, retrieval, CLI, adapters) build on stable, tested contracts.

## Scope

### In Scope

- Phase 0 - Bootstrap: uv-compatible `pyproject.toml` (src/ layout, Python >=3.12), package skeleton (10 subpackages), Ruff/mypy/pytest config, minimal CLI stub (`ragfence --help`), `docker-compose.yml` (PG16 + pgvector), `.github/workflows/ci.yml`, Apache-2.0 LICENSE, README.md, CONTRIBUTING.md stub, `.env.example` (placeholders only).
- Phase 1 - Core models: enums (`Classification`, `DocumentStatus`, `FindingSeverity`, `ScenarioOutcome`) and Pydantic v2 models (`AuthorizationContext`, `DocumentACL`, `DocumentPolicy`, `PolicyDecision`, `RetrievalRequest`, `RetrievedChunk`, `Citation`, `AttackScenario`, `EvaluationCase`, `SecurityFinding`, `EvaluationResult`); protocols (`RAGAdapter`, `VectorStore`, `LLMProvider`, `EmbeddingProvider`); ACL decision flow (deny-by-default, authorization before retrieval); `AuthorizationContext` jsonb serialization.
- Phase 2 - Storage: SQLAlchemy 2.x models for all 13 BACKEND_SCHEMA tables; Alembic chain 0001-0004 (base, enums, tables, HNSW + GIN indexes); `vector(1536)` default; normalized ACL columns vs JSONB metadata rule; repositories with `deleted_at` soft-delete filters. DB-gated integration tests skipped without a DB; unit tests run without Docker.

### Out of Scope

Attack engine (P7), generic HTTP adapter (P9), real LLM providers (P10), full CLI commands (P6), Acme Corp dataset (P3), demo UI.

## Capabilities

> Contract for sdd-spec. `openspec/specs/` is empty; all capabilities are new.

### New Capabilities

- `project-bootstrap`: packaging, tooling, CI, license, local services (Phase 0).
- `domain-models`: canonical enums, models, protocols (Phase 1).
- `policy-engine`: ACL deny-by-default decision flow, authorization before retrieval (Phase 1).
- `storage-schema`: ORM models, Alembic migrations, pgvector, repositories (Phase 2).

### Modified Capabilities

None - no existing specs.

## Approach

- Phase 0: uv-compatible pyproject; local verification via venv+pip (uv not installed). No business logic.
- Phase 1: pure models, zero I/O; decision flow as a pure function over `DocumentPolicy` + `AuthorizationContext` -> `PolicyDecision` (TRD §5.3, rules 1-9).
- Phase 2: DDL owned by Alembic (ORM never creates tables); ACL fields as typed columns; JSONB `metadata` never consulted for access decisions.
- Delivery: 3 review slices (one per phase), each within the 400-line budget, via auto-chain.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `pyproject.toml`, `src/ragfence/` | New | Packaging, skeleton, core/policies/db modules |
| `alembic/` | New | Migration chain 0001-0004 |
| `docker-compose.yml`, `.github/workflows/ci.yml` | New | Local services, CI (lint/type/test) |
| `LICENSE`, `README.md`, `CONTRIBUTING.md`, `.env.example` | New | Release basics |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Python 3.14 wheel gaps (pydantic/SQLAlchemy/pgvector) | Med | Pin compatible versions; CI matrix on 3.12; verify via venv+pip |
| pgvector type unregistered in Alembic migrations | Med | Explicit DDL for vector columns; idempotent `upgrade head` test |
| Scope creep across 3 phases | Med | Slice per phase; tasks forecast the 400-line budget |

## Rollback Plan

All-new files; nothing deployed. Slice revert = git revert/delete of that slice's files. DB rollback = `alembic downgrade base`; no live data exists pre-release.

## Dependencies

- Python >=3.12 (local 3.14.5); venv+pip; Docker optional (compose/integration tests).
- Packages: pydantic v2, SQLAlchemy 2.x, Alembic, psycopg, pgvector, Typer. No API keys.

## Success Criteria

- [ ] `python -m pytest` green without Docker; `ruff check`/`format` and `mypy strict` clean.
- [ ] All canonical TRD names import and validate; enum ordering enforced.
- [ ] Policy decision table: `engineering_employee` vs CFO.pdf -> DENY with reasons.
- [ ] With DB present: `alembic upgrade head` idempotent; HNSW + GIN indexes exist.

## Open Questions

- CI matrix floor: 3.12 only, or 3.12-3.14 given the local 3.14.5?
- Which pgvector image tag to pin in `docker-compose.yml`?
