# RAGFence — Implementation Plan

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** engineering and project management
**Scope:** sequential, dependency-ordered implementation phases for the RAGFence v0.1 release.

Canonical model names used in this document (defined in `TRD.md`): `AuthorizationContext`, `DocumentACL`, `RetrievalRequest`, `RetrievedChunk`, `RAGAdapter`, `AttackScenario`, `EvaluationCase`, `EvaluationResult`, `SecurityFinding`, `DocumentPolicy`.

---

## Conventions

- **Complexity:** S = small (≤ 1–2 days), M = medium (≤ 1 week), L = large (1–3 weeks).
- **Each phase is independently shippable** and ends with a green test suite.
- Phases must be executed in order; each phase lists the phases it depends on.
- Schema changes land through Alembic migrations only.

---

## Phase 0 — Repository Bootstrap

**Dependencies:** none.

**Deliverables**
- Repo initialized with `pyproject.toml` (`uv`), `src/` layout (`src/ragfence/`).
- Empty package skeleton: `ragfence/cli`, `core`, `auth`, `policies`, `retrieval`, `evaluation`, `attacks`, `adapters`, `providers`, `observability`.
- Tooling config: Ruff, mypy, pytest; `Makefile`-free scripts in `pyproject.toml`.
- `docker-compose.yml` for PostgreSQL 16 + pgvector.
- GitHub Actions workflow skeleton (`ci.yml`: lint, typecheck, test).
- LICENSE (Apache-2.0), `.gitignore`, `.env.example`, `CONTRIBUTING.md` stub.

**Architecture**
- No business logic yet; prove the packaging and tooling contract (`uv sync`, `uv run pytest`, `uv run ragfence --help`).

**Tests**
- Smoke test: `ragfence --help` returns 0; an empty package import test.

**Acceptance criteria**
- `uv run ruff check`, `uv run mypy src`, `uv run pytest` all green on a clean checkout.
- `docker compose up` starts a healthy pgvector instance.
- CI runs the same three checks.

**Security considerations**
- `.env.example` contains placeholders only; no secrets in the repo.
- Dependencies pinned; lockfile committed.

**Complexity:** S

---

## Phase 1 — Core Domain Models

**Dependencies:** Phase 0.

**Deliverables**
- Enums: `Classification`, `DocumentStatus`, `FindingSeverity`, `ScenarioOutcome` (`core/enums.py`).
- Pydantic v2 models exactly as specified in `TRD.md` §3: `AuthorizationContext`, `DocumentACL`, `DocumentPolicy`, `PolicyDecision`, `RetrievalRequest`, `RetrievedChunk`, `Citation`, `AttackScenario`, `EvaluationCase`, `SecurityFinding`, `EvaluationResult`.
- Protocol stubs: `RAGAdapter`, `VectorStore`, `LLMProvider`, `EmbeddingProvider`.
- Serialization helpers for `AuthorizationContext` (jsonb round-trip).

**Architecture**
- Pure models, zero I/O. The `AuthorizationContext.source` field records provenance (`synthetic`/`oidc`/`api_token`).

**Tests**
- Pydantic validation: malformed classification, missing tenant, top_k bounds.
- `PolicyDecision` semantics: reasons list populated, deny-by-default default.
- Enum ordering (`public < internal < confidential < restricted`).

**Acceptance criteria**
- All domain names match `TRD.md`; all models import cleanly and validate.
- mypy strict passes.

**Security considerations**
- `AuthorizationContext` has no field that accepts client-supplied parameters; `RetrievalRequest.filters` is documented as server-normalized.

**Complexity:** S

---

## Phase 2 — PostgreSQL + pgvector

**Dependencies:** Phase 1.

**Deliverables**
- SQLAlchemy 2.x models for the full schema in `BACKEND_SCHEMA.md` (13 tables + enums).
- Alembic migration chain: `0001` base, `0002` enums, `0003` tables, `0004` indexes (incl. HNSW vector index, GIN ACL indexes).
- `PgVectorStore` implementing the `VectorStore` protocol (embedding search with `vector_cosine_ops`).
- Repository layer for tenants/users/departments/groups/user_groups/documents/document_acl/document_chunks.
- Config wiring: `ragfence.toml` `[database]` + `RAGFENCE_DATABASE_DSN` env override.

**Architecture**
- SQLAlchemy 2.0 typed ORM; migrations own the DDL; the ORM never creates tables implicitly.
- `updated_at` maintained via server-side trigger.

**Tests**
- Migration applies cleanly from scratch and is idempotent (`upgrade head` twice).
- Repository CRUD incl. soft-delete semantics (`deleted_at IS NULL` filters).
- `PgVectorStore.search` returns ordered results by cosine similarity.

**Acceptance criteria**
- Fresh DB: `ragfence db upgrade head` leaves the schema exactly as documented.
- All schema-level constraints enforced (unique keys, FKs, enum values).

**Security considerations**
- Connection strings loaded from env/config, never hardcoded; no credentials in migrations.
- SQL built with bound parameters only (no string interpolation).

**Complexity:** M

---

## Phase 3 — Synthetic Organization Dataset

**Dependencies:** Phase 2.

**Deliverables**
- Acme Corp seed: tenants `acme-corp` + `globex-corp`; departments `engineering`, `hr`, `finance`, `legal`, `executive`; synthetic users with argon2 password hashes; groups (`payroll-admins`, `legal-review`); `user_groups`.
- Synthetic document corpus with known classifications and ACLs, including the trap fixture `finance/payroll/CFO.pdf` (department `finance`, classification `confidential`) and at least one soft-deleted document.
- Deterministic chunker + `FakeEmbeddingProvider` (fixed seed) so embeddings are reproducible across machines.
- Seed idempotency: re-seeding does not duplicate rows.

**Architecture**
- Seed module (`ragfence/attacks/fixtures/`) plus a `seed` command under `ragfence init --with-demo` / `ragfence db seed`.

**Tests**
- Determinism: seeding twice produces identical checksums and embeddings.
- Fixture integrity: every document has an ACL row; every chunk has a tenant and a valid `chunk_index`.
- Cross-tenant fixtures exist for both tenants.

**Acceptance criteria**
- `ragfence test` on an empty-but-seeded DB finds the expected trap documents.
- No external network or API key needed to seed.

**Security considerations**
- Synthetic data only; no real PII. The CFO salary fixture value is a fake, deliberately memorable value so leakage is detectable in answers.

**Complexity:** M

---

## Phase 4 — Authorization Engine

**Dependencies:** Phase 1, Phase 3.

**Deliverables**
- `PolicyEngine` in `policies/` implementing the deny-by-default decision flow from `TRD.md` §5.3.
- `AuthorizationContextBuilder` in `auth/` that resolves identity → directory → context server-side.
- Auth endpoint (reference MVP): `POST /api/v1/auth/login` (username + password → signed token) and a `GET /api/v1/authz/context` viewer.
- Policy predicate builder producing the SQL filter from `BACKEND_SCHEMA.md` §9.1.

**Architecture**
- Authentication (who) and authorization (what may you see) live in separate modules; the token carries only identity, never permissions.
- `source: synthetic` recorded on every context.

**Tests**
- Decision table tests covering all 9 rules in §5.3 (incl. deleted, non-ready, cross-tenant, role-escalation, explicit allow, department allow, no-grant deny).
- AuthZ context derived from backend directory — forged client headers (`X-Tenant`, `X-Role`) are ignored.
- AuthN: wrong password fails; expired token fails.

**Acceptance criteria**
- `PolicyEngine` returns `PolicyDecision` with reasons for every input.
- The engineering_employee vs `finance/payroll/CFO.pdf` case resolves to DENY.

**Security considerations**
- Tokens: short-lived, signed, not stored in plaintext; password hashes argon2.
- The builder never reads tenant/department/role from request headers or query params.

**Complexity:** M

---

## Phase 5 — Secure Retrieval

**Dependencies:** Phase 2, Phase 4.

**Deliverables**
- `RetrievalService` orchestrating: embed query → build policy predicate → `PgVectorStore.search` on the allowed subset → rerank → context assembly → `Citation[]`.
- Query-time enforcement: the vector search executes **only** against rows passing the policy predicate (single SQL statement; no post-hoc filtering).
- Citation assembly from `RetrievedChunk`s.
- Latency capture (`retrieval_latency_ms`) into `RetrievalRequest` flow.

**Architecture**
- One SQL statement per search: `WHERE policy_predicate ... ORDER BY embedding <=> :q LIMIT :top_k`. No client-supplied filter keys reach the SQL.

**Tests**
- Cross-tenant, cross-department, deleted, non-ready, and restricted chunks never appear in results.
- Retrieval over the whole Acme corpus is correct and within v0.1 latency budget.
- `top_k` honored; over-request clamped server-side.

**Acceptance criteria**
- Leakage rate = 0 on the reference implementation for the v0.1 scenario set.

**Security considerations**
- No fallback path exists: if the predicate fails to build, the search errors closed.

**Complexity:** M

---

## Phase 6 — CLI

**Dependencies:** Phase 3, Phase 5.

**Deliverables**
- Typer commands: `ragfence init` (scaffold config + Compose + seed), `ragfence test` (run suites; `--adapter`, `--base-url`, `--threshold`, `--json`), `ragfence demo` (start reference service), `ragfence adapter` (validate `generic_http`).
- Report renderer implementing `UI_UX_DESIGN_BRIEF.md` §2 (severity colors, progress, exit codes 0/1/2).
- Config loading (`ragfence.toml`) + env overrides; `.ragfence/reports/` writer (txt + json).

**Architecture**
- CLI is a thin shell over `evaluation` and `adapters`; no business logic in `cli/`.

**Tests**
- Command-level integration tests (pytest + subprocess or Typer runner).
- Exit codes: pass=0, below-threshold=1, config error=2.
- Non-TTY rendering is plain (no ANSI).

**Acceptance criteria**
- `pip install ragfence` in a fresh venv → `ragfence init` → `ragfence test` → report in under 5 minutes with zero external keys.

**Security considerations**
- Secret inputs only via env, never echoed; report JSON contains evidence but redacts chunk content by default.

**Complexity:** M

---

## Phase 7 — Attack Engine

**Dependencies:** Phase 3, Phase 6.

**Deliverables**
- All 10 v0.1 `AttackScenario` definitions (`PRD.md` §4.D) with generators producing `EvaluationCase`s (prompt + actor + `expected_allow`).
- Scenario executor that runs a case against a target adapter and collects `RetrievedChunk[]`, answer, and latency.
- Verdict logic: expected_allow vs observed behavior; leak detection via fixture ground truth (e.g. CFO salary value appearing in answer).

**Architecture**
- `attacks/` holds declarative scenarios; `evaluation/` holds the executor — scenario definitions never execute anything themselves.
- Each scenario declares `target_stage` (`retrieval`/`generation`/`both`) so adapter-less generation scenarios can skip cleanly.

**Tests**
- Generator determinism (same seed → same cases).
- Each scenario runs against the reference implementation and yields the expected outcome (blocked cases pass).

**Acceptance criteria**
- 10 scenario classes present; every "must block" case passes against the reference implementation.

**Security considerations**
- The engine is a test harness, not an exploit tool: synthetic data only, no live targets, bounded timeouts.

**Complexity:** M

---

## Phase 8 — Evaluation / Reporting

**Dependencies:** Phase 7.

**Deliverables**
- `EvaluationEngine`: suite orchestration (cases → runs → results → findings), weighted scoring (0–100), scenario outcome derivation (PASS/WARNING/FAIL/CRITICAL).
- Persistence of `evaluation_suites`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, `security_findings`.
- Report rendering + JSON artifact.
- Threshold enforcement and exit-code logic (shared with Phase 6).

**Architecture**
- Metrics computed in `evaluation/metrics.py`: context precision/recall (retrieval), faithfulness/answer correctness (generation), leakage rate + unauthorized retrieval rate (security), latency, cost.
- All persisted results are reproducible from stored evidence.

**Tests**
- Scoring math (weights, threshold boundary).
- Finding severity → outcome mapping.
- Persistence round-trip and idempotent re-runs.

**Acceptance criteria**
- A full `ragfence test` run populates all 5 evaluation tables with coherent, queryable data.

**Security considerations**
- Evidence jsonb redacts secrets and truncates chunk content per `observability` rules.

**Complexity:** M

---

## Phase 9 — Generic HTTP Adapter

**Dependencies:** Phase 6, Phase 8.

**Deliverables**
- `GenericHTTPAdapter` implementing `RAGAdapter` (`retrieve`, `answer`, `is_healthy`) against configurable `retrieve_path`/`answer_path`.
- Adapter config schema in `ragfence.toml` (`[adapters.generic_http]`); `ragfence adapter check`.
- Response mapping → `RetrievedChunk[]` with strict parsing (Pydantic); malformed responses fail the case.
- `is_healthy` retry with backoff.

**Architecture**
- The adapter is the only component that speaks to external systems; everything above it works on `RetrievalRequest`/`RetrievedChunk`.

**Tests**
- Against a local FastAPI stub: happy path, non-JSON response, missing fields, timeouts.
- Evidence capture: prompts, responses, verdicts in `security_findings.evidence`.

**Acceptance criteria**
- `ragfence test --adapter generic_http --base-url <stub>` produces a full report with evidence.

**Security considerations**
- Auth header template supports static bearer tokens only (documented); no credential logging.

**Complexity:** M

---

## Phase 10 — Optional LLM Provider

**Dependencies:** Phase 8.

**Deliverables**
- `LLMProvider` implementations: `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider` (local), `FakeLLMProvider`.
- BYOK wiring: `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` env; `OllamaProvider` with base URL.
- Generation metrics (faithfulness, answer correctness) enabled only when a real provider is configured; otherwise generation scenarios report `WARNING`/skipped.

**Architecture**
- `providers/llm.py` behind the protocol; evaluation never imports vendor SDKs directly.

**Tests**
- Fake provider determinism; provider selection logic; token counting; error handling (rate limit → retry/backoff, failure → case failed).

**Acceptance criteria**
- With a real key, generation scenarios run end-to-end; without one, the suite still passes deterministically using the fake provider.

**Security considerations**
- Keys never logged; provider responses recorded only as `LLMResponse.content` in evidence (truncated).

**Complexity:** M

---

## Phase 11 — CI Integration

**Dependencies:** Phase 8, Phase 9.

**Deliverables**
- Reusable GitHub Actions workflow (`ragfence-test.yml`): checkout → install → `ragfence init --up` → start target → `ragfence test --adapter <target> --threshold N` → upload JSON artifact → PR comment summary.
- Threshold-driven gating: exit 1 blocks the PR (branch protection).
- Determinism guard: suite must produce identical scores across CI runs (fake providers by default).

**Architecture**
- The workflow is a thin wrapper over the CLI; all behavior lives in the product so local and CI behavior match.

**Tests**
- Manual: push a PR that degrades a scenario → check fails; fix → check passes.
- GitHub Actions matrix on Python 3.12.

**Acceptance criteria**
- A purposefully broken scenario turns the check red and the PR cannot merge.

**Security considerations**
- CI secrets stored as GitHub secrets; DB credentials for CI use throwaway DSN.

**Complexity:** S

---

## Phase 12 — Open Source Release Readiness

**Dependencies:** Phases 0–11.

**Deliverables**
- Full docs pass (PRD/TRD/APP_FLOW/UI_UX/BACKEND_SCHEMA/IMPLEMENTATION_PLAN aligned), README with quickstart, contribution guide, code-of-conduct, changelog.
- Packaging verification: `uv build` + `pip install` from the wheel in a clean venv.
- Example configurations for reference and `generic_http` targets; example adapter stub project.
- Performance sanity pass on Acme Corp (embedding + search within v0.1 budget).
- Public CI green on `main`.

**Architecture**
- No feature additions in this phase; only hardening and proof of the release contract.

**Tests**
- Install-from-wheel smoke test on a fresh machine/container.
- End-to-end: init → seed → test → report on a clean environment.

**Acceptance criteria**
- `pip install ragfence` works from PyPI artifact; `ragfence test` produces the documented report under 5 minutes with no external keys; docs internally consistent (names match `TRD.md`).

**Security considerations**
- Pre-release audit: no secrets in history, `.env.example` only, dependency audit (`uv audit`/`pip-audit`) clean.

**Complexity:** M

---

## Dependency Graph

```
Phase 0
 └─▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 6 ──▶ Phase 7 ──▶ Phase 8 ──▶ Phase 9 ──▶ Phase 11
                 └───────────▶ Phase 5 (needs Phase 2 + Phase 4)
                               Phase 4 (needs Phase 1 + Phase 3)
                                        Phase 10 (needs Phase 8)
                                                    └─▶ Phase 12 (needs all)
```

## Risk Notes

- **Phase 3 is the correctness anchor.** Deterministic embeddings and fixtures are what make every later phase's verdict trustworthy; do not proceed to Phase 4 with a non-deterministic seed.
- **Phase 5 is the security anchor.** If the predicate ever degrades to post-hoc filtering, the product's core promise ("never retrieve unauthorized chunks") is broken; a test asserting `leakage rate = 0` is non-negotiable here.
- **Scope control:** adapters beyond `generic_http`, a web UI, and enterprise auth are explicitly out of v0.1 and must not be pulled into these phases.
