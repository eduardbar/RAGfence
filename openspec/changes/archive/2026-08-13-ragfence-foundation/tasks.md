# Tasks: RAGFence Foundation (Phases 0-2)

## Review Workload Forecast

Estimated changed lines: total ~1500-2100 (S1 ~300-500, S2 ~600-800, S3 ~600-800)

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test | Runtime harness | Rollback |
|------|------|----|--------------|-----------------|---------|
| 1 | Installable pkg + gates | PR 1 | `python -m pytest`; `ragfence --help` | `pip install -e .` venv | revert pyproject/ + src/ |
| 2 | Models + policy | PR 2 | `python -m pytest tests/unit/` | `mypy` core/ + policies/ | revert core/ + policies/ + providers/ |
| 3 | ORM + migrations | PR 3 | `python -m pytest -m db` (skips w/o DB) | `alembic upgrade head` x2 PG16 | `alembic downgrade base`; revert db/ + alembic/ |

Commit units: one Conventional Commit per task; tests with code.

## Phase 1: Bootstrap (PR 1)

- [x] 1.1 Create `pyproject.toml` (src/ layout, >=3.12, deps, `ragfence` entry, Ruff/mypy/pytest). Test: `python -m pytest` green; `pip install -e .` imports.
- [x] 1.2 Create `src/ragfence/` + 11 subpackage stubs (core, policies, providers, cli, db, auth, retrieval, evaluation, attacks, adapters, observability). Test: import each.
- [x] 1.3 Create Typer stub `src/ragfence/cli/main.py`. Test: CliRunner `--help` exit 0.
- [x] 1.4 Create `docker-compose.yml` (pgvector/pgvector:pg16, healthcheck, port). Verify: `docker compose config` parses.
- [x] 1.5 Create `.github/workflows/ci.yml` (3.12; ruff check/format, mypy strict, pytest).
- [x] 1.6 Create `LICENSE` (Apache-2.0), `README.md`, `CONTRIBUTING.md`, `.env.example` placeholders. Test: no secrets.
- [x] 1.7 Gates: `python -m pytest`, `ruff check`, `ruff format --check`, `mypy` green without Docker.

## Phase 2: Domain Models (PR 2)

- [x] 2.1 RED->GREEN `src/ragfence/core/enums.py`: 4 str enums + Classification rank. Test: values, ordering, invalid member rejected.
- [x] 2.2 RED->GREEN `src/ragfence/core/models.py`: 11 Pydantic v2 models per TRD 3.2-3.5. Test: valid construction; invalid input rejected.
- [x] 2.3 RED->GREEN JSONB round-trip in `core/models.py` (`model_validate_json(model_dump_json())`). Test: lossless, `source` preserved.
- [x] 2.4 RED->GREEN `src/ragfence/core/protocols.py` (RAGAdapter, VectorStore, LLMProvider, EmbeddingProvider) + fakes in `src/ragfence/providers/`. Test: mypy conformance, zero I/O.

## Phase 3: Policy Engine (PR 2)

- [x] 3.1 RED->GREEN `src/ragfence/policies/decision.py`: pure `decide(policy, ctx) -> PolicyDecision`, rules 4-9 (escalation, grants, dept, deny-by-default). Test: CFO.pdf DENY, escalation DENY, allowlist ALLOW, same-dept ALLOW, reasons named (CFO.pdf).
- [x] 3.2 RED->GREEN auth-before-retrieval: load active/ready/tenant (rules 1-3) then decide; DENY blocks retrieval (Denied request never retrieves).

## Phase 4: Storage Schema (PR 3)

- [x] 4.1 RED->GREEN `src/ragfence/db/base.py` + `db/models.py`: 13 ORM tables, Mapped[...], sa.Enum(create_type=False), ACL ARRAY(Uuid) `'{}'`, `documents.deleted_at`; `create_all` forbidden. Test: ORM metadata vs `docs/BACKEND_SCHEMA.md`.
- [x] 4.2 Create `alembic/` env.py + chain 0001 base -> 0002 enums (CREATE TYPE x5) -> 0003 tables (Vector(1536)) -> 0004 indexes (HNSW + GIN x2).
- [x] 4.3 DB-gated tests `tests/integration/`: upgrade x2 idempotent; HNSW/GIN present; soft-delete; tenant isolation.
- [x] 4.4 RED->GREEN `src/ragfence/db/repositories.py`: shared base filtering `deleted_at.is_(None)` + tenant scope on every read.
- [x] 4.5 RED->GREEN ACL predicate uses typed columns only, never JSONB `metadata`.
- [x] 4.6 `tests/conftest.py` DB probe + `@pytest.mark.db` skip("PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN").
