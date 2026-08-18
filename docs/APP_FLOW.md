# RAGFence — Application Flows

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** engineering and operations
**Scope:** step-by-step journeys through the RAGFence CLI and reference implementation, including states, error paths, and interaction points.

Canonical model names used in this document (defined in `TRD.md`): `AuthorizationContext`, `DocumentACL`, `RetrievalRequest`, `RetrievedChunk`, `RAGAdapter`, `AttackScenario`, `EvaluationCase`, `EvaluationResult`, `SecurityFinding`, `DocumentPolicy`.

---

## Journey 1 — Developer Quickstart

Goal: a fresh developer runs the full local security test suite in under 5 minutes, without external API keys.

### Flow

```
$ pip install ragfence
$ ragfence init
$ ragfence test
RAGFence Security Report
✓ Cross-tenant isolation
✓ Department isolation
...
Score: 82/100
```

### States

1. **Installed.** `pip install ragfence` (or `uv add ragfence`). CLI on PATH; `ragfence --version` prints the version.
2. **Configured.** `ragfence init` scaffolds:
   - `ragfence.toml` (defaults: database DSN `postgresql+psycopg://ragfence:ragfence@localhost:5432/ragfence`, embedding dimension 1536, `FakeEmbeddingProvider` + `FakeLLMProvider`, evaluation threshold 80).
   - `docker-compose.yml` (postgres + pgvector image, one command).
   - `.env.example` (secret placeholders; no real keys).
   - Acme Corp synthetic dataset manifests.
   - `.ragfence/` working directory for reports and evidence.
3. **Database ready.** `ragfence init --up` starts Compose, applies Alembic migrations, and seeds Acme Corp (`tenants`, `users`, `departments`, `groups`, `user_groups`, `documents`, `document_acl`, `document_chunks`). Idempotent: re-running is a no-op for existing data.
4. **Report produced.** `ragfence test` runs the configured target (the deterministic local reference seam by default, or `--adapter generic_http --base-url ...` for an external target) and writes:
   - Human report to stdout and `.ragfence/reports/latest.txt`.
   - With `--json`, a machine-readable artifact at `.ragfence/reports/latest.json`.
5. **Exit codes.** `0` = completed evaluation meets threshold; `1` = completed evaluation is below threshold; `2` = configuration, usage, reachability, or runtime failure.

### Error paths

| Error | Symptom | Recovery |
|---|---|---|
| Missing config | `Error: ragfence.toml not found. Run 'ragfence init'.` | Run `ragfence init` |
| No database | `Error: could not connect to PostgreSQL ...` | `ragfence init --up` (or set `RAGFENCE_DATABASE_DSN`) |
| Vector dimension mismatch | `Error: embedding dimension 384 != vector(1536)` | Align `[embeddings]` with schema; re-run migrations |
| Adapter not reachable | `Error: adapter generic_http not healthy: connect ECONNREFUSED` | Verify `--base-url`, auth header, retry |
| Migration drift | `Error: alembic history diverges` | `ragfence db upgrade head` after a pull |
| Port already in use | Compose fails to bind `5432` | Change `RAGFENCE_DATABASE_DSN` port mapping in Compose |

---

## Journey 2 — Secure RAG Demo (Reference Implementation)

Goal: demonstrate end-to-end that authorization happens **before** retrieval and **before** the LLM context is assembled.

### Flow

```
Login (synthetic user) ──▶ token
        │
        ▼
POST /api/v1/chat  { question, top_k }   ← question is user data; that's all
        │
        ▼
Authentication (token → user) ──▶ AuthorizationContext  (server-side directory lookup)
        │
        ▼
ACL Policy Engine (deny-by-default over documents) ──▶ allowed document set
        │
        ▼
Filtered vector retrieval (SQL predicate ∧ ANN) ──▶ RetrievedChunk[]
        │
        ▼
Reranking → context assembly → LLM → Citation[]
        │
        ▼
200 { answer, citations }
```

### Actor example — the PRD scenario

| Field | Value |
|---|---|
| User | `engineering_employee` |
| Login | `engineering_employee@acme-corp.test` |
| Question | "What is the CFO salary?" |
| Target doc | `finance/payroll/CFO.pdf` (department `finance`, classification `confidential`) |
| Expected response | `403 ACCESS DENIED` — not an LLM answer |

### Behavior details

- **Authorization context viewer**: the reference service exposes `GET /api/v1/authz/context` (or a demo UI tab) returning the resolved `AuthorizationContext` for the current token: `tenant_id`, `department_id`, `classification`, `allowed_group_ids`. This is the debugging surface that answers "what is the system allowed to see for me?".
- **Blocked-before-LLM evidence**: every chat response carries response headers `X-RAGFence-Policy: allow|deny`, `X-RAGFence-Documents-Allowed: <n>`, and `X-RAGFence-Retrieval-Ms: <ms>`. The demo UI shows the policy decision, the filtered retrieval trace, and (for the engineering_employee example) the explicit denial: no chunk from `finance/payroll/CFO.pdf` was retrieved, so the LLM never saw it.
- **Cross-tenant check**: logging in as `globex_corp` user and asking about an `acme_corp` document yields the same `ACCESS DENIED`; tenant mismatch is denied at rule 3 of the policy decision flow.

### States

- `anonymous` → `authenticated` (login) → `authorized` (context resolved) → `retrieved` (filtered chunks) → `answered` (citations) | `denied` (policy block).
- Denial is a terminal state for that request: no LLM call is made, so no generation can leak the forbidden content.

### Error paths

| Error | HTTP | Behavior |
|---|---|---|
| Invalid/expired token | 401 | `error: invalid_token`; no context built |
| Missing/invalid question | 422 | Pydantic validation |
| No documents match filter | 200 | Empty citations; `X-RAGFence-Documents-Allowed: 0` |
| Policy decision denied | 403 | `error: access_denied` + reasons array; no retrieval, no LLM |
| LLM provider failure | 502 | Answer absent; retrieval evidence retained |

---

## Journey 3 — CI Flow

Goal: a PR that degrades retrieval security fails the build. Works in GitHub Actions (and any runner that can execute the CLI).

### Flow

```
PR opened ──▶ workflow: checkout + install ragfence
                 │
                 ▼
           start RAG service (reference impl or adapter target, via Compose)
                 │
                 ▼
           ragfence test --adapter generic_http --base-url <svc> --threshold 80
                 │
                 ├── Score >= threshold ──▶ PASS (exit 0) ──▶ job green
                 └── Score <  threshold ──▶ FAIL (exit 1) ──▶ job red, PR blocked
```

### Threshold semantics

- `--threshold N` (default from `[evaluation] threshold = 80`). The run fails when `score < threshold`.
- Threshold is evaluated against the **weighted scenario score**, not per-case, so teams can tune tolerance. For security-critical repos, a threshold of 100 is typical.
- `EvaluationCase`-level results are persisted regardless of pass/fail, so a failing PR produces a reviewable artifact (`ragfence` job summary + JSON evidence) explaining exactly which attack scenario regressed.

### CI contract

- Determinism: synthetic data and fake providers mean the same local input yields the same score; flaky external LLM answers are not part of the default score.
- A below-threshold evaluation returns exit code `1`; configuration, reachability, or runtime failures return `2`.
- Docker Compose/PostgreSQL + pgvector is an optional database prerequisite, not part of the offline CLI/adapter checks.
- A future repository workflow may upload `.ragfence/reports/latest.json`; this documentation does not claim a public CI receipt.

### Error paths

| Error | Behavior |
|---|---|
| RAG service not ready | `is_healthy()` retries with backoff; after timeout, job fails with `adapter not healthy` |
| Database not migrated | `ragfence init --up` step before `test`; failure halts |
| No scenarios configured | `Warning: suite has 0 cases`; job fails (empty suite is not a pass) |
| Test run crashed mid-suite | Run marked `failed`; partial results retained; exit 1 |

---

## Journey 4 — Adapter Flow (External RAG System)

Goal: point RAGFence at an existing RAG system and get a security score without changing that system's internals.

### Adapter contract (from `TRD.md`)

```python
class RAGAdapter(Protocol):
    name: str
    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]: ...
    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str: ...
    def is_healthy(self) -> bool: ...
```

`GenericHTTPAdapter` implements this against configurable endpoints:

```toml
[adapters.generic_http]
base_url = "http://localhost:8000"
retrieve_path = "/retrieve"     # POST {question, top_k}
answer_path = "/chat"           # optional; POST {question, context}
auth_header = "Authorization"   # optional static bearer for the target
```

### Flow

```
existing RAG ──config──▶ ragfence adapter (generic_http)
                              │
        ragfence test --adapter generic_http --base-url http://...
                              │
                              ▼
        synthetic queries (Acme Corp prompts + actors) ──▶ observe retrieve()/answer()
                              │
                              ▼
        map responses → RetrievedChunk[] / answer strings
                              │
                              ▼
        score (leakage rate, unauthorized retrieval rate, context precision, ...)
                              │
                              ▼
        evidence file (queries, responses, verdicts) + report
```

### Evidence collection

For every `EvaluationCase`, the adapter records:

- The exact prompt and the actor's `AuthorizationContext` (synthetic identity).
- What the target returned (chunks, scores, answer), or that it errored.
- RAGFence's verdict: leaked / blocked / errored, mapped to a `SecurityFinding` with severity and the scenario id.

Because the synthetic dataset has known ground truth (Acme Corp ACLs), any unauthorized chunk or answer derived from forbidden content is a mechanical detection — no LLM judgment involved.

### Error paths

| Error | Symptom | Recovery |
|---|---|---|
| Target unreachable | `is_healthy()` false → run aborts | Fix base URL / auth / firewall |
| Non-JSON response | Adapter raises `AdapterParseError`; case marked failed | Inspect evidence JSON; align `retrieve_path` contract |
| Target ignores `top_k` | Adapter detects mismatch; `WARNING` finding | Document in evidence; tune adapter |
| Target returns metadata spoofing fields | Adapter strips them; logs `metadata-spoofing` signal | None needed; evidence records it |
| No answer endpoint | Generation scenarios skipped with `WARNING`, retrieval scenarios still scored | Enable `answer_path` for full coverage |

---

## Cross-Cutting Consistency Notes

- Every journey terminates in artifacts persisted to the same tables (`evaluation_runs`, `evaluation_results`, `security_findings`) so CLI, demo, CI, and adapter flows share one audit trail.
- Deny-by-default applies everywhere: a missing config, a failed health check, an empty suite, and an unauthorized request are all treated as *not allowed* rather than *proceed optimistically*.
