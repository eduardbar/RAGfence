# RAGFence — Backend Schema Design

**Tagline:** Security testing and authorization-aware retrieval for production RAG systems.

**Document status:** v0.1 draft
**Audience:** engineering
**Scope:** the initial PostgreSQL schema for the reference implementation and evaluation store. PostgreSQL 16 + pgvector.

Canonical model names used in this document (defined in `TRD.md`): `AuthorizationContext`, `DocumentACL`, `RetrievalRequest`, `RetrievedChunk`, `RAGAdapter`, `AttackScenario`, `EvaluationCase`, `EvaluationResult`, `SecurityFinding`, `DocumentPolicy`.

---

## 1. Conventions

- **Primary keys:** `uuid` (server-generated `gen_random_uuid()`). All PKs named `id`.
- **Timestamps:** `timestamptz`, UTC, named `created_at` / `updated_at` / `deleted_at`. `updated_at` maintained by triggers or ORM.
- **Soft delete:** `deleted_at timestamptz null`; a row is active when `deleted_at IS NULL`. **All queries filter on this.** This is the deletion mechanism for the deleted-document-retrieval attack scenario.
- **Enums:** Postgres `ENUM` types, created in migration `0002`.
- **Naming:** `snake_case`, plural table names, singular enum values.
- **Deny-by-default policy:** enforced in code by the ACL Policy Engine; the schema additionally supports it via filtered retrieval predicates (see §9). The schema never stores an "allow all" document flag.
- **Checksums:** SHA-256, hex-encoded, lowercase.

---

## 2. Enum Types

```sql
CREATE TYPE classification AS ENUM ('public','internal','confidential','restricted');
CREATE TYPE document_status AS ENUM ('pending','ready','failed');
CREATE TYPE finding_severity AS ENUM ('low','medium','high','critical');
CREATE TYPE run_status AS ENUM ('running','passed','failed','crashed');
CREATE TYPE scenario_outcome AS ENUM ('pass','warning','fail','critical');
```

`classification` ordering: `public < internal < confidential < restricted` (used in §9 rank checks).

---

## 3. Table: `tenants`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `name` | text | NOT NULL | — | Display name, e.g. "Acme Corp" |
| `slug` | text | NOT NULL | — | Unique, e.g. `acme-corp` |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`slug`).

Relationship: 1–N to `users`, `departments`, `groups`, `documents`, `document_acl`, `document_chunks`.

---

## 4. Table: `users`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)` |
| `department_id` | uuid | NULL | — | FK → `departments(id)` |
| `email` | text | NOT NULL | — | Login identifier |
| `password_hash` | text | NOT NULL | — | Argon2 hash (reference MVP auth) |
| `display_name` | text | NOT NULL | — | |
| `classification` | classification | NOT NULL | `'internal'` | Max clearance level |
| `is_active` | boolean | NOT NULL | `true` | |
| `created_at` | timestamptz | NOT NULL | `now()` | |
| `updated_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`tenant_id`, `email`); INDEX (`department_id`); INDEX (`tenant_id`, `is_active`).

Relationships: N–1 `tenants`, N–1 `departments`, N–M `groups` via `user_groups`.

Synthetic fixture (Acme Corp): `engineering_employee@acme-corp.test` (engineering, `internal`), `finance_analyst@acme-corp.test` (finance, `confidential`), `legal_counsel@acme-corp.test` (legal, `restricted`).

---

## 5. Table: `departments`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)` |
| `name` | text | NOT NULL | — | e.g. "Engineering" |
| `slug` | text | NOT NULL | — | e.g. `engineering` |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`tenant_id`, `slug`).

Acme Corp seed: `engineering`, `hr`, `finance`, `legal`, `executive`.

---

## 6. Table: `groups`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)` |
| `name` | text | NOT NULL | — | e.g. "payroll-admins" |
| `slug` | text | NOT NULL | — | |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`tenant_id`, `slug`).

Relationships: N–M to `users` via `user_groups`; referenced by `document_acl.allowed_group_ids`.

---

## 7. Table: `user_groups` (join)

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `user_id` | uuid | NOT NULL | — | FK → `users(id)`; PK part 1 |
| `group_id` | uuid | NOT NULL | — | FK → `groups(id)`; PK part 2 |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Primary key: (`user_id`, `group_id`). Index on (`group_id`) for reverse lookups.

---

## 8. Table: `documents`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)`; isolation boundary #1 |
| `department_id` | uuid | NULL | — | FK → `departments(id)`; isolation boundary #2 (NULL = no implicit dept access) |
| `title` | text | NOT NULL | — | e.g. "CFO Payroll Summary" |
| `source` | text | NOT NULL | — | e.g. `acme-synthetic`, or external source URI |
| `checksum` | text | NOT NULL | — | SHA-256 of ingested content |
| `classification` | classification | NOT NULL | `'internal'` | |
| `status` | document_status | NOT NULL | `'pending'` | `ready` → retrievable |
| `version` | integer | NOT NULL | `1` | Increments on re-ingest |
| `created_at` | timestamptz | NOT NULL | `now()` | |
| `updated_at` | timestamptz | NOT NULL | `now()` | |
| `deleted_at` | timestamptz | NULL | — | Soft delete marker |

Indexes: UNIQUE (`tenant_id`, `checksum`); INDEX (`tenant_id`, `status`); INDEX (`department_id`); PARTIAL INDEX (`deleted_at IS NULL`).

Relationships: 1–N to `document_acl` (one ACL row per document), 1–N to `document_chunks`.

Soft delete semantics: setting `deleted_at` excludes the document and its chunks from every retrieval predicate; the row remains for audit.

---

## 9. Table: `document_acl`

Per-document access rules (1:1 with `documents`).

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | uuid | NOT NULL | — | FK → `documents(id)`; UNIQUE |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)` (denormalized for query) |
| `department_id` | uuid | NULL | — | FK → `departments(id)` (denormalized; mirrors document) |
| `classification` | classification | NOT NULL | `'internal'` | Denormalized for filter predicate |
| `allowed_user_ids` | uuid[] | NOT NULL | `'{}'` | Explicit user allowlist |
| `allowed_group_ids` | uuid[] | NOT NULL | `'{}'` | Explicit group allowlist |
| `created_at` | timestamptz | NOT NULL | `now()` | |
| `updated_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`document_id`); INDEX (`tenant_id`, `classification`); GIN (`allowed_user_ids`), GIN (`allowed_group_ids`).

### 9.1 Policy resolution (evaluation at query time)

Given a user's `AuthorizationContext` (`tenant_id`, `department_id`, `classification`, `allowed_group_ids`) and a `document_acl` row, the access rule is:

```
allowed =
  documents.deleted_at IS NULL
  AND documents.status = 'ready'
  AND document_acl.tenant_id = ctx.tenant_id
  AND rank(document_acl.classification) <= rank(ctx.classification)
  AND (
        ctx.user_id = ANY(document_acl.allowed_user_ids)
     OR ctx.allowed_group_ids && document_acl.allowed_group_ids
     OR (
          document_acl.department_id IS NOT NULL
          AND document_acl.department_id = ctx.department_id
        )
  )
```

- Department-scoped documents are readable by members of that department by default (Acme Corp convention).
- Cross-department and cross-tenant access requires an explicit ACL grant.
- Everything else is denied (deny-by-default).

The retrieval query embeds this predicate as SQL; the pgvector ANN search runs only on the allowed subset.

---

## 10. Table: `document_chunks`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `document_id` | uuid | NOT NULL | — | FK → `documents(id)` |
| `tenant_id` | uuid | NOT NULL | — | FK → `tenants(id)` (denormalized for filters) |
| `chunk_index` | integer | NOT NULL | — | 0-based order |
| `content` | text | NOT NULL | — | Chunk text |
| `embedding` | vector(1536) | NULL | — | pgvector; dim configurable via settings |
| `metadata` | jsonb | NOT NULL | `'{}'` | Chunker-specific extras (never used for access decisions) |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: UNIQUE (`document_id`, `chunk_index`); INDEX (`tenant_id`); HNSW vector index on `embedding` (`vector_cosine_ops`).

### 10.1 Metadata: normalized vs JSONB

- **Normalized columns** (`tenant_id`, `document_id`, and the ACL fields reachable through `document_acl`): these participate in security filters and are compared with exact, typed values. Normalization is what makes the predicate in §9.1 correct and non-spoofable.
- **JSONB `metadata`**: chunker-specific extras — source URL, page numbers, headings, table captions, provenance strings. They are surfaced in `RetrievedChunk.metadata` for evidence but are **never consulted by the policy engine**. This keeps the schema flexible without weakening the filter surface.

---

## 11. Table: `evaluation_suites`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `name` | text | NOT NULL | — | e.g. `default`, `ci-gate` |
| `description` | text | NULL | — | |
| `target_adapter` | text | NOT NULL | — | e.g. `reference`, `generic_http` |
| `threshold` | integer | NOT NULL | `80` | Minimum score (0–100) |
| `created_at` | timestamptz | NOT NULL | `now()` | |
| `updated_at` | timestamptz | NOT NULL | `now()` | |

Relationships: 1–N to `evaluation_cases`, 1–N to `evaluation_runs`.

---

## 12. Table: `evaluation_cases`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `suite_id` | uuid | NOT NULL | — | FK → `evaluation_suites(id)` |
| `scenario_id` | text | NOT NULL | — | FK-like → `AttackScenario.id` (declarative) |
| `prompt` | text | NOT NULL | — | The adversarial question |
| `actor` | jsonb | NOT NULL | — | Serialized synthetic `AuthorizationContext` |
| `expected_allow` | boolean | NOT NULL | — | Derived from scenario `expected_behavior` |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: INDEX (`suite_id`, `scenario_id`).

The `actor` jsonb snapshot keeps historical cases reproducible even if the directory changes later.

---

## 13. Table: `evaluation_runs`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `suite_id` | uuid | NOT NULL | — | FK → `evaluation_suites(id)` |
| `status` | run_status | NOT NULL | `'running'` | `passed`/`failed`/`crashed` |
| `score` | numeric(5,2) | NULL | — | Weighted 0–100 |
| `threshold` | integer | NOT NULL | `80` | Snapshot of suite threshold |
| `result` | scenario_outcome | NULL | — | Overall outcome |
| `started_at` | timestamptz | NOT NULL | `now()` | |
| `finished_at` | timestamptz | NULL | — | |

Indexes: INDEX (`suite_id`, `started_at`).

Relationships: 1–N to `evaluation_results`, 1–N to `security_findings`.

---

## 14. Table: `evaluation_results`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `run_id` | uuid | NOT NULL | — | FK → `evaluation_runs(id)` |
| `case_id` | uuid | NOT NULL | — | FK → `evaluation_cases(id)` |
| `passed` | boolean | NOT NULL | — | Case verdict |
| `outcome` | scenario_outcome | NOT NULL | — | Derived from findings |
| `retrieved_chunk_ids` | uuid[] | NOT NULL | `'{}'` | Evidence: chunks the target returned |
| `answer` | text | NULL | — | Target answer (truncated preview) |
| `latency_ms` | integer | NOT NULL | — | |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: INDEX (`run_id`, `case_id`); INDEX (`run_id`, `passed`).

Relationships: 1–N to `security_findings`.

---

## 15. Table: `security_findings`

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `id` | uuid | NOT NULL | `gen_random_uuid()` | PK |
| `result_id` | uuid | NULL | — | FK → `evaluation_results(id)`; NULL if finding is not case-bound |
| `run_id` | uuid | NOT NULL | — | FK → `evaluation_runs(id)` |
| `case_id` | uuid | NULL | — | FK → `evaluation_cases(id)` |
| `severity` | finding_severity | NOT NULL | — | `low`/`medium`/`high`/`critical` |
| `category` | text | NOT NULL | — | e.g. `unauthorized-retrieval`, `prompt-injection`, `metadata-spoofing` |
| `title` | text | NOT NULL | — | Short, e.g. "Cross-tenant chunk leaked into context" |
| `description` | text | NOT NULL | — | Detail + remediation hint |
| `evidence` | jsonb | NOT NULL | `'{}'` | Prompts, chunks, timestamps, adapter responses |
| `created_at` | timestamptz | NOT NULL | `now()` | |

Indexes: INDEX (`run_id`, `severity`); INDEX (`category`); INDEX (`case_id`).

---

## 16. ER Summary

```
tenants 1─N users  N─M groups (via user_groups)
   │           │
   │           └─N─1 departments
   │
   ├─N documents 1─1 document_acl
   │       │
   │       └─N document_chunks
   │
   └─N evaluation_suites 1─N evaluation_cases
             │
             └─N evaluation_runs 1─N evaluation_results
                            │        └─N security_findings
                            └─N security_findings
```

---

## 17. Security & Performance Notes

- **Denormalized ACL/tenant columns** on `document_chunks` and `document_acl` exist so the security predicate runs as a single-index filter before ANN search; keep them in sync within a transaction at write time.
- **Soft delete is a write, not a drop** — retention preserves the audit trail that security evaluation depends on.
- **Never use JSONB `metadata` in policy predicates.** Doing so would reopen the metadata-spoofing attack class.
- pgvector HNSW supports approximate nearest neighbors; filtered search degrades gracefully at small scale (Acme Corp), which is acceptable for v0.1 and for local evaluation workloads.
