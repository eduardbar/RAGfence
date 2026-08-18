# Design: RAGFence Foundation (Phases 0-2)

## Technical Approach

Greenfield foundation implementing Phases 0-2 as four capabilities: bootstrap, domain-models, policy-engine, storage-schema. Pure core first (zero I/O, no Docker/keys); storage second behind a thin seam. Strict TDD: every spec scenario is a RED test first. Delivery: 3 auto-chained PR slices within the 400-line budget.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Layout | flat vs src/ | `src/ragfence/`, uv-compatible pyproject | TRD §1; venv+pip (no uv) |
| Policy split | all-9-pure vs split | 4-9 pure in `policies/`; 1-3 (deleted_at, status, tenant) in storage | Pure fn can't read row state; spec-required. CONFIRMED |
| DB driver | sync psycopg vs asyncpg | Sync `postgresql+psycopg://` | TRD §11 DSN; async deferred to FastAPI |
| DDL ownership | `create_all` vs Alembic-only | Alembic-only; `create_all` forbidden | Migrations own DDL |
| Protocol home | per-package vs one module | All 4 in `core/protocols.py`; SQL via TYPE_CHECKING | Spec groups them pure; core stays ORM-free |
| ACL typing | JSONB vs normalized columns | Typed `ARRAY(Uuid)` + enum cols; JSONB `metadata` never consulted | TRD §4.3: exact, non-spoofable predicate |
| DB-gated tests | always-run vs skipif | `@pytest.mark.db` + probe skipif | Skip with reason; unit green without Docker |
| Main specs | sync vs empty-until-archive | `openspec/specs/` stays empty (`.gitkeep`) | OpenSpec: merged at sdd-archive |

## Module Layout (src/ragfence/)

| Package | In THIS change | Stub/empty |
|---|---|---|
| `core/` | `enums.py`, `models.py`, `protocols.py` (full) | — |
| `policies/` | `decision.py` (rules 4-9) | — |
| `providers/` | FakeLLMProvider, FakeEmbeddingProvider | real (P10) |
| `cli/` | Typer stub (`--help`) | commands (P6) |
| `db/` | `base.py`, `models.py`, `repositories.py` | PgVectorStore (P5) |
| `auth/`, `retrieval/` | stubs | builder (P4), service (P5) |
| `evaluation/`, `attacks/`, `adapters/`, `observability/` | empty stubs | P7-P10 |

`db/` supplements TRD's 10; `InMemoryVectorStore` is a `tests/support/` double.

## Policy Engine

```python
def decide(policy: DocumentPolicy, ctx: AuthorizationContext) -> PolicyDecision
```

`policies/decision.py`, deterministic, no I/O; `reasons` name failing rules. JSONB round-trip: `model_validate_json(model_dump_json())` normalizes list to `set[UUID]`; `source` preserved.

| # | Rule | Decision |
|---|---|---|
| 4 | classification rank > ctx rank | DENY (escalation) |
| 5 | `ctx.user_id in policy.allowed_user_ids` | ALLOW |
| 6 | group ids intersect | ALLOW |
| 7 | dept id None, no grant above | DENY (no implicit access) |
| 8 | dept id == ctx dept | ALLOW |
| 9 | else | DENY |

5-6 precede 7-8 (grants override dept); rule 4 first.

## SQLAlchemy Model Design

`db/models.py`: all 13 tables, `Mapped[...]`; enums `sa.Enum(..., create_type=False)` (DDL 0002); ACL ids `ARRAY(Uuid)` default `'{}'`; only `documents` has `deleted_at`. Repos (shared base) filter `deleted_at.is_(None)` and tenant-scope reads. Relationships per §16.

## Alembic Migration Strategy

Top-level `alembic/`; `env.py` imports `db.models`. Chain: `0001` base → `0002` enums (`CREATE TYPE` x5) → `0003` tables (explicit `Vector(1536)`) → `0004` indexes (HNSW + GIN x2). Version table makes a second `upgrade head` a no-op; test runs twice.

## Data Flow

Auth before retrieval (1-3 storage, 4-9 pure):

```
Caller → RetrievalService → DocumentRepository: load (active, ready, tenant) [1-3]
       → decide(policy, ctx) [4-9] → PolicyDecision
       allowed → VectorStore.search(...)   # never on DENY
       denied  → DENY + reasons; zero retrieval calls
```

DB-gated skip:

```
@pytest.mark.db → conftest probe: connect(DSN, 1s)
  unreachable → skip("PostgreSQL unavailable; set RAGFENCE_TEST_DATABASE_DSN")
  reachable → fixture alembic upgrade head; run
```

## File Changes (key)

| File | Action | Description |
|---|---|---|
| `pyproject.toml`, `src/ragfence/**` | Create | Packaging, skeleton, Typer stub |
| `alembic/` | Create | Chain, vector(1536), HNSW/GIN |
| `docker-compose.yml`, `.github/workflows/ci.yml` | Create | PG16+pgvector; CI gates |
| `LICENSE`, `README.md`, `CONTRIBUTING.md`, `.env.example` | Create | Apache-2.0; placeholders |
| `tests/`, `tests/support/` | Create | Unit, fakes, DB-gated integration |

## Testing Strategy

| Capability | Unit (no Docker/keys) | Integration |
|---|---|---|
| bootstrap | import; `--help` exit 0; gates | compose config; CI |
| domain-models | enums, validation, JSONB round-trip, mypy | none |
| policy-engine | decision table (CFO.pdf, escalation, grants, dept, no-grant); denied never retrieves | none |
| storage-schema | ORM metadata vs BACKEND_SCHEMA (no DB) | DB-gated: upgrade x2, indexes, soft-delete, tenant |

TDD order: bootstrap → domain-models → policy-engine → storage, each RED-first.

## Threat Matrix

All 5 rows N/A: no routing, shell, subprocess, git, or PR logic. CI uses stock actions; CLI stub is fixed `--help` (Phase 6); compose static. Entry/CI behavior covered by bootstrap scenarios as RED tests.

## Migration / Rollout

No data migration (greenfield). Rollback: git revert per slice; DB = `alembic downgrade base`. 3 auto-chained PR slices.

## Open Questions

None — CI matrix, compose tag, license, dim, soft-delete resolved.
