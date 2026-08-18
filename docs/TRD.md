# RAGFence — Technical Requirements Document

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** engineering
**Scope:** architecture, domain model, interfaces, data flow, and operational concerns for the RAGFence v0.1 release.

---

## 1. Architecture Overview

RAGFence is a Python 3.12+ package distributed with `pyproject.toml` (preferred tool: `uv`), using a `src/` layout (`src/ragfence/`). It exposes a CLI (`ragfence`) built on Typer and is importable as a library. The reference implementation is a FastAPI service backed by PostgreSQL + pgvector via SQLAlchemy 2.x and Alembic migrations.

The system is composed of two cooperating surfaces:

1. **Secure reference implementation** — a full RAG pipeline that enforces authorization before retrieval. Ships as a FastAPI app plus the library modules.
2. **Security evaluation engine** — an attack-driver that runs adversarial scenarios against any target (the reference implementation or an external RAG system via an adapter) and produces evaluation reports.

The evaluation engine is the product's primary deliverable; the reference implementation is the proof that the enforced pipeline is practical.

---

## 2. Core Packages

```
ragfence/
├── cli/             # Typer commands: init, test, demo, adapters
├── core/            # domain models, enums, shared value objects
├── auth/            # authentication resolution + AuthorizationContext builder
├── policies/        # ACL policy engine, deny-by-default decisions
├── retrieval/       # filtered vector retrieval, reranking, citations
├── evaluation/      # evaluation cases, runs, results, report rendering
├── attacks/         # AttackScenario library (the 10 v0.1 scenarios)
├── adapters/        # RAGAdapter contract + generic_http implementation
├── providers/       # LLM + embedding provider abstractions (BYOK, fake defaults)
└── observability/   # structured logging, tracing helpers, redaction
```

Each package exists because it owns a distinct responsibility with a concrete consumer:

| Package | Responsibility | Why it exists (not overengineering) |
|---|---|---|
| `cli` | Command surface | Typer entry points are the primary UX; keeps console logic out of libraries |
| `core` | Domain models | `AuthorizationContext`, `RetrievalRequest`, enums are shared by every layer; a single home prevents import cycles |
| `auth` | Identity → authorization context | The security-critical transform; isolated so it can be audited and swapped (synthetic users now, OIDC later) |
| `policies` | Access decisions | The enforcement point; deliberately separate from retrieval so deny-by-default is never bypassed by a search tweak |
| `retrieval` | Filtered search + answer assembly | Owns the post-policy pipeline: embedding query, ANN search, rerank, citations |
| `evaluation` | Test orchestration + reporting | The product core; consumes cases and produces `EvaluationResult` |
| `attacks` | Scenario definitions | Declarative data + generators; kept separate from evaluation mechanics |
| `adapters` | Target abstraction | Lets one evaluation engine test the reference implementation OR an external RAG system |
| `providers` | Model/embedding interchange | BYOK + fake defaults for tests; a thin seam, no plugin framework |
| `observability` | Logging/redaction | Security tooling must log decisions without logging secrets or documents |

No additional abstractions (no plugin systems, no dependency-injection containers, no hexagonal ports beyond the two protocols that genuinely need them: `RAGAdapter` and `LLMProvider`/`EmbeddingProvider`).

---

## 3. Domain Abstractions

These names are **canonical and used identically** in `BACKEND_SCHEMA.md`, `APP_FLOW.md`, and `IMPLEMENTATION_PLAN.md`.

### 3.1 Core enums

```python
class Classification(str, Enum):
    PUBLIC = "public"          # 0
    INTERNAL = "internal"      # 1
    CONFIDENTIAL = "confidential"  # 2
    RESTRICTED = "restricted"  # 3

class DocumentStatus(str, Enum):
    PENDING = "pending"    # ingested, not yet ready
    READY = "ready"        # retrievable
    FAILED = "failed"      # ingestion error

class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ScenarioOutcome(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    CRITICAL = "critical"
```

`ScenarioOutcome` is the severity axis for CLI/report output (PASS, WARNING, FAIL, CRITICAL). `FindingSeverity` grades individual `SecurityFinding` records (LOW/MEDIUM/HIGH/CRITICAL). A scenario outcome is derived from its findings.

### 3.2 Authorization

```python
class AuthorizationContext(BaseModel):
    tenant_id: UUID
    user_id: UUID
    department_id: UUID | None
    classification: Classification
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]
    is_authenticated: bool
    source: Literal["synthetic", "oidc", "api_token"]  # how identity was established

class DocumentACL(BaseModel):
    document_id: UUID
    tenant_id: UUID
    department_id: UUID | None
    classification: Classification
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]

class DocumentPolicy(BaseModel):
    """Declarative access rule for a document. v0.1 supports one rule form:
    department-scoped with optional explicit user/group allowlist."""
    classification: Classification
    department_id: UUID | None
    allowed_user_ids: set[UUID]
    allowed_group_ids: set[UUID]

class PolicyDecision(BaseModel):
    allowed: bool
    reasons: list[str]          # human- and machine-readable rationale
    evaluated_at: datetime
```

The `AuthorizationContext` is **always derived server-side from the authenticated identity** (see §6). The `source` field records provenance for auditability. `DocumentACL` is the persisted shape (DB row); `DocumentPolicy` is the in-memory rule used by the policy engine.

### 3.3 Retrieval

```python
class RetrievalRequest(BaseModel):
    query: str
    authorization: AuthorizationContext
    top_k: int = 10
    filters: dict[str, Any] = {}   # normalized, server-side only; never raw client params

class RetrievedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    chunk_index: int
    content: str
    score: float
    metadata: dict[str, Any]       # normalized + JSONB extras, merged for evidence

class Citation(BaseModel):
    document_id: UUID
    document_title: str
    chunk_index: int
    snippet: str
```

`RetrievalRequest.filters` is a **server-normalized** dict built inside the reference service. Client-supplied filter parameters are validated and mapped into this shape or dropped; arbitrary client keys are never honored (metadata-spoofing defense).

### 3.4 Adapter contract

```python
class RAGAdapter(Protocol):
    """Any RAG system RAGFence can evaluate against."""
    name: str

    def retrieve(self, request: RetrievalRequest) -> list[RetrievedChunk]: ...
    def answer(self, request: RetrievalRequest, chunks: list[RetrievedChunk]) -> str: ...
    def is_healthy(self) -> bool: ...
```

Implementations: `GenericHTTPAdapter` (v0.1), in-process `ReferenceImplementationAdapter`. LangChain/LlamaIndex adapters are backlog items built on the same protocol.

### 3.5 Evaluation

```python
class AttackScenario(BaseModel):
    id: str                       # e.g. "cross-tenant-retrieval"
    name: str
    description: str
    target_stage: Literal["retrieval", "generation", "both"]
    expected_behavior: Literal["must_block", "must_allow"]

class EvaluationCase(BaseModel):
    id: UUID
    scenario_id: str              # FK to AttackScenario
    prompt: str
    actor: AuthorizationContext   # synthetic identity acting in the case
    expected_allow: bool          # derived from scenario.expected_behavior

class SecurityFinding(BaseModel):
    id: UUID
    severity: FindingSeverity
    category: str                 # e.g. "unauthorized-retrieval", "prompt-injection"
    title: str
    description: str
    evidence: dict[str, Any]      # prompts, retrieved chunks, timestamps

class EvaluationResult(BaseModel):
    id: UUID
    case_id: UUID
    passed: bool
    findings: list[SecurityFinding]
    retrieved: list[RetrievedChunk]
    answer: str | None
    latency_ms: int
```

### 3.6 Data flow (one evaluation)

```
AttackScenario ──generates──▶ EvaluationCase ──> adapter.retrieve(RetrievalRequest)
                                                     │
                                                     ├─▶ RetrievedChunk[] (+ optional adapter.answer)
                                                     ▼
                                              EvaluationResult (findings, passed)
                                                     │
                                                     ▼
                                              Report (per-scenario PASS/WARNING/FAIL/CRITICAL + Score)
```

---

## 4. RAG Pipeline (Reference Implementation)

### 4.1 Ingestion

Documents are ingested via the reference service. Pipeline stages:

1. **Chunking** — deterministic chunker (fixed chunk size, overlap); chunk index preserved.
2. **Embeddings** — via `EmbeddingProvider` (§9); deterministic seeds for synthetic data.
3. **Metadata** — each chunk carries normalized fields + JSONB extras (see §4.3).
4. **ACL** — the document's `DocumentACL` is persisted; `allowed_user_ids`/`allowed_group_ids` are stored and indexed.
5. **Soft delete** — `documents.deleted_at`; deleted documents and their chunks are excluded from all queries.

### 4.2 Query-time pipeline

```
Authentication ──▶ AuthorizationContext
                         │
                         ▼
              ACL Policy Engine ──deny-by-default──▶ PolicyDecision
                         │ (allowed only)
                         ▼
         Filtered Vector Retrieval (SQL: tenant+dept+class+ACL ∧ vector search)
                         │
                         ▼
              Reranking (over filtered set only)
                         │
                         ▼
              Context assembly → LLM → Citations
```

### 4.3 Where authorization is enforced — and why metadata normalization matters

- **Authorization is enforced BEFORE retrieval, at query time.** The policy engine produces a set of allowed documents; the SQL that feeds the vector search includes the policy predicate. The vector index is never queried without the filter. This is the difference between "deny after retrieving" and "never see the chunk".
- **Metadata normalization matters** because filters must be compared against canonical, typed values. `tenant_id`, `department_id`, `classification`, and ACL references are **normalized columns** in `document_chunks`/`document_acl` (UUIDs and enums), so a `WHERE` clause on them is exact. Chunker-specific extra metadata (source URL, page numbers, headings) is stored as JSONB in `document_chunks.metadata` and is **never** used for access decisions. If a chunk's ACL-relevant metadata lived in JSONB, a typo or spoofed value could bypass the filter.

---

## 5. Authorization Model

### 5.1 Schema concept

Each document carries:

| Field | Meaning |
|---|---|
| `tenant_id` | Owning tenant; isolation boundary #1 |
| `department_id` | Owning department (nullable); isolation boundary #2 |
| `classification` | `public` ≤ `internal` ≤ `confidential` ≤ `restricted` |
| `allowed_users` / `allowed_groups` | Explicit allowlist (ACL) |

A user's `AuthorizationContext` carries `tenant_id`, `department_id`, `classification` (their max clearance), and their group/user IDs.

### 5.2 Source of truth

The authorization context is derived from the **authenticated backend identity**, never from arbitrary user-supplied parameters. The reference service resolves the identity from its own authentication layer (§5.4) and looks up the directory (users, groups, departments) in PostgreSQL. Any tenant/department/role headers or query parameters sent by the client are ignored for decision purposes; they may be logged as a metadata-spoofing signal.

### 5.3 Policy decision flow (deny-by-default)

```
decision(document, ctx):
  1. if document.deleted_at is not NULL            → DENY  (deleted-document attack)
  2. if document.status != READY                   → DENY
  3. if document.tenant_id != ctx.tenant_id        → DENY  (cross-tenant attack)
  4. if rank(document.classification) > rank(ctx.classification) → DENY  (role escalation)
  5. if ctx.user_id in document.allowed_user_ids   → ALLOW
  6. if ctx.allowed_group_ids ∩ document.allowed_group_ids → ALLOW
  7. if document.department_id is None              → DENY  (no implicit dept access)
  8. if document.department_id == ctx.department_id → ALLOW
  9. else                                          → DENY
```

Rules 7–8 mean department-scoped documents are visible to members of that department by default (that is the Acme Corp convention), while cross-department access requires an explicit ACL grant. Everything not explicitly allowed is denied.

### 5.4 Authentication (reference MVP)

Authentication and authorization are **separate** concerns.

- Identity source: synthetic users table in PostgreSQL (`users`, `departments`, `groups`, `user_groups`).
- Mechanism: a lightweight demo auth — synthetic users authenticate with a username + password hash (argon2), exchanging credentials for a short-lived signed token (HMAC-signed JWT or opaque session token) at `/api/v1/auth/login`.
- No enterprise OAuth/SSO in v0.1. The `AuthorizationContext.source` field marks synthetic origin so the same code path is ready for an OIDC adapter later.

Flow: `identity → authentication → authorization context → policy engine → retrieval`. Authentication answers "who are you?"; authorization answers "what may you see?".

---

## 6. Vector Storage

- **MVP:** PostgreSQL + pgvector. `document_chunks.embedding` is a `vector(1536)` column (default dimension; configurable via a documented setting). ANN search uses a pgvector HNSW index (or IVF for smaller sets).
- **Portability:** retrieval depends on a thin seam — `retrieval` queries against a `VectorStore` interface with one implementation (`PgVectorStore`). The interface is defined now to keep the SQL isolated, but there is **no** connector framework; pgvector is the only implementation in v0.1. Future stores (Qdrant, Weaviate, Milvus) implement the same interface when the project has a concrete user need.

```python
class VectorStore(Protocol):
    def search(self, *, embedding: list[float], policy_predicate: SQL, top_k: int) -> list[RetrievedChunk]: ...
```

---

## 7. LLM Providers

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, *, messages: list[Message], temperature: float) -> LLMResponse: ...

class LLMResponse(BaseModel):
    content: str
    prompt_tokens: int
    completion_tokens: int
```

- Implementations: `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider` (local), and `FakeLLMProvider` (deterministic, used in tests and when no key is present).
- **No mandatory provider.** BYOK: credentials come from environment variables or config; the reference config defaults to `FakeLLMProvider` so `ragfence test` runs with zero external dependencies.
- Providers are wired behind the protocol; the evaluation engine never calls a vendor SDK directly.

---

## 8. Embeddings

```python
class EmbeddingProvider(Protocol):
    name: str
    dimension: int
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

- Same philosophy as LLM providers: OpenAI, Hugging Face/local (Ollama, sentence-transformers), and `FakeEmbeddingProvider` for determinism in tests.
- The synthetic Acme Corp corpus is embedded once with a deterministic provider so evaluations are reproducible across machines.
- Dimension mismatch between provider and `vector(1536)` column is validated at startup.

---

## 9. Evaluation

Three independent evaluation kinds, all exposed through `evaluation` and the CLI:

1. **Retrieval evaluation** — did the target retrieve the right *allowed* chunks? Metrics: **context precision**, **context recall**.
2. **Generation evaluation** — did the answer stay faithful to the retrieved context? Metrics: **faithfulness**, **answer correctness**.
3. **Security evaluation** — did the target block or leak? Metrics: **leakage rate** (unauthorized content that reached the answer), **unauthorized retrieval rate** (unauthorized chunks that reached the result set).

Cross-cutting operational metrics: **latency** (ms) and **cost** (tokens consumed).

Conceptual scoring: the report aggregates scenario outcomes into a 0–100 weighted score (default weight 1 per scenario; configurable). `EvaluationResult.passed` is per-case; scenario outcome is PASS if all its cases pass, WARNING/FAIL/CRITICAL depending on the severity of findings.

---

## 10. Observability

Structured logging (JSON) with consistent fields:

```
request_id, user_id, tenant_id, policy (decision id), allowed,
retrieval_latency_ms, chunks_returned, top_k_requested,
model (llm provider), prompt_tokens, completion_tokens,
evaluation_run_id, scenario_id, security_findings (severity + category)
```

Redaction guarantees:

- **Never log secrets** — API keys, tokens, password hashes.
- **Never log full documents** — chunk content is truncated to a configurable preview (default 200 chars) and only in evidence contexts that opt in; the reference service redacts `RetrievedChunk.content` in access logs.
- **Never log the authorization context fields derived from unauthenticated input** — the `source` is always logged, the identity only after authentication.

---

## 11. Configuration Surface

Primary file: `ragfence.toml` (created by `ragfence init`). Key sections:

```toml
[server]        # reference implementation bind, base URL
[database]      # DSN: postgresql+psycopg://user:pass@localhost:5432/ragfence
[embeddings]    # provider, model, dimension
[llm]           # provider, model, temperature
[evaluation]    # suite, threshold (default 80), weights
[adapters.generic_http]  # base_url, auth header template, endpoints
```

Environment variables override config for secrets (`RAGFENCE_DATABASE_DSN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).

---

## 12. Technology Summary

| Concern | Choice |
|---|---|
| Language | Python 3.12+ |
| Web | FastAPI |
| Validation | Pydantic v2 |
| ORM/migrations | SQLAlchemy 2.x, Alembic |
| Storage | PostgreSQL + pgvector |
| CLI | Typer |
| Tests | pytest |
| Local services | Docker Compose (postgres + pgvector image) |
| Lint/type | Ruff, mypy |
| CI | GitHub Actions |
| Packaging | `pyproject.toml`, `uv`, `src/` layout |
