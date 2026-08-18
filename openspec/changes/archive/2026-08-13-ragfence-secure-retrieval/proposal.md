# Proposal: Secure Retrieval Service (Phase 5)

## Intent

Deliver the security anchor of RAGFence: a `RetrievalService` that enforces authorization BEFORE retrieval (TRD §4.2, IMPLEMENTATION_PLAN Phase 5). `retrieval/` is currently a stub; policy enforcement exists (`guard_retrieval`, `decide`) but nothing orchestrates a filtered, citation-bearing vector retrieval over an `AuthorizationContext`. A DENY must never reach the vector store, and retrieval must run only against ACL-allowed rows (single SQL predicate, no post-hoc filtering) so leakage rate stays 0.

## Scope

### In Scope

- `RetrievalService` in `retrieval/`: accepts `RetrievalRequest` + `AuthorizationContext`.
- Guard BEFORE retrieval: row state (active/ready/tenant), `decide()`; DENY returns typed denial with reasons, no vector call.
- ALLOW path: `build_acl_predicate` (typed columns only, never JSONB metadata) + `VectorStore.search` (InMemory for tests; PgVectorStore via repositories for DB).
- `RetrievedChunk[]` + `Citation[]` assembly (document title/source/checksum, chunk index, score).
- Structured per-request retrieval trace: attempted, allowed/blocked, reasons.
- TDD tests: DENY never calls store (count calls); same-dept ALLOW; classification-escalation DENY; metadata-spoofing no-op; trace records decision+reasons; citations carry provenance; DB-gated path retrieves only allowed rows.

### Out of Scope

Reranking, LLM call/context assembly (generation), attack engine (P7), evaluation runner (P8), CLI wiring (P6), real LLM providers (P10).

## Capabilities

### New Capabilities

- `secure-retrieval`: filtered vector retrieval gated by authorization-before-retrieval, citation provenance, and per-request trace.

### Modified Capabilities

None — consumes `domain-models`, `policy-engine`, `storage-schema`, `auth-context`, `synthetic-dataset` contracts unchanged.

## Approach

- `retrieval/service.py`: orchestrate embed → predicate → `VectorStore.search` → citations. Reuse `decide` + `guard_retrieval` row-state seam; build predicate via `build_acl_predicate`.
- `retrieval/trace.py`: immutable `RetrievalTrace` (request id, decision, reasons, store_call_count, latency_ms).
- `retrieval/citations.py`: `Citation[]` from `RetrievedChunk[]`.
- Tests use a counting `VectorStore` double (records `search` calls) + `InMemoryVectorStore`; DB path gated by `RAGFENCE_TEST_DATABASE_DSN`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ragfence/retrieval/` | New | service, trace, citations |
| `tests/` (retrieval tests) | New | deny/allow, spoof, trace, citations, gated DB |
| `tests/support/vector_store.py` | New/Modified | counting double |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Predicate degrades to post-hoc filtering | Low | Single-statement contract; deny-never-calls-store test |
| Metadata spoofing via JSONB | Low | Predicate uses typed columns only; dedicated no-op test |
| DB/unit divergence | Med | Shared predicate; DB tests gated + mirrored unit tests |

## Rollback Plan

New files only; no schema/migration changes. Revert = delete `src/ragfence/retrieval/` additions and retrieval tests; no deployed state affected.

## Dependencies

- Phases 1–4: `domain-models` (`RetrievalRequest`, `RetrievedChunk`, `Citation`), `policy-engine` (`decide`, `guard_retrieval`), `storage-schema` (`build_acl_predicate`), `auth-context`, `synthetic-dataset`.
- Python 3.14.5, venv+pip, pytest; PostgreSQL reachable for DB-gated tests (port 5434).

## Success Criteria

- [ ] `python -m pytest` green; DENY tests prove zero vector-store calls.
- [ ] Cross-tenant/department/deleted/non-ready/restricted chunks never returned (leakage 0).
- [ ] `top_k` honored; citations carry provenance; trace records decision + reasons.
- [ ] DB-gated path retrieves only allowed rows.
- [ ] Within 400-line review budget; auto-chain (stacked-to-main) if exceeded.

## Proposal question round

Assumptions for user review: (1) service consumes an already-built `AuthorizationContext` (auth-context does the building) and the `RetrievalRequest.authorization` field; (2) DENY is a typed result carrying reasons + empty chunks (not an exception), so the caller/trace sees the denial; (3) citation `snippet` truncates chunk content (observability redaction default); (4) reranking and generation stay backlog. Correct or run a second round on request.
