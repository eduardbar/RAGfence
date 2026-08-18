# Design: Secure Retrieval Service

## Technical Approach

A `RetrievalService` in `src/ragfence/retrieval/` orchestrates **authorization-before-retrieval** over a `VectorStore`: load row state (rules 1-3), run `decide()` (rules 4-9), and only on ALLOW search the store with `build_acl_predicate` passed down as a single SQL predicate, then assemble citations. DENY returns a typed `SecureRetrievalResult` with empty chunks and **zero store calls** (proved by a counting double). Maps to proposal approach; implements `secure-retrieval` spec reqs 1-6.

## Architecture Decisions

| # | Decision | Options / tradeoff | Choice | Rationale |
|---|----------|--------------------|--------|-----------|
| ADR-1 | DENY representation | (a) exception (b) typed result | **(b) typed `SecureRetrievalResult`** with `reasons`, empty `chunks` | Spec req 1 mandates no exception; caller/trace inspect the denial; mirrors `GuardedResult`. |
| ADR-2 | Guard placement | (a) guard inside service only (b) reuse `guard_retrieval` per-doc | **(b) generalize the guard seam, single choke point** — service runs row-load + decide once per request, then filtered store search | req 2: DENY must precede ANY store call; one choke point keeps leakage 0. `guard_retrieval`'s per-doc `Retriever` is too narrow for corpus-wide top-k, so the service reuses `DocumentRowState` + `decide` directly. |
| ADR-3 | Filtering strategy | (a) post-filter result set (b) pre-filter single SQL predicate | **(b) predicate passed INTO `VectorStore.search`** | req 3: one statement, never post-hoc; typed columns only (never JSONB `metadata`); `InMemoryVectorStore` accepts-and-ignores, counting double + DB path assert it. |
| ADR-4 | Citation provenance | (a) extend `Citation` model (b) reuse as-is | **(a) extend `Citation`** with `source`, `checksum`, `score` (bounded defaults) | req 4 mandates title/source/checksum/chunk_index/score; existing `Citation`/`RetrievedChunk` lack source+checksum. Contract delta to `domain-models`, flagged in Open Questions. |
| ADR-5 | Citation snippet | (a) full content (b) truncated default | **(b) truncate** to ~200 chars (redaction) | req 4: observability-safe; full content stays on `RetrievedChunk` for internal use. |
| ADR-6 | Trace | (a) plain dict (b) immutable typed `RetrievalTrace` | **(b) typed, immutable** | req 5: request_id, decision, reasons, chunk count, latency_ms, store_call_count; no docs/secrets. |

## Data Flow

```
DENY flow (rules 1-3 / 4-9 fail):
  retrieve(request)
    └─ load row state ──► decide() ──► DENY
        └─► SecureRetrievalResult(decision=DENY, reasons=[...], chunks=[])
        └─► trace(store_call_count=0)      ← zero VectorStore.search calls

ALLOW flow:
  retrieve(request)
    └─ load row state (active/ready/tenant) ──► decide() ──► ALLOW
        └─► store.search(embedding, policy_predicate=build_acl_predicate, top_k)
              └─► RetrievedChunk[] (top_k, ACL-allowed only)
        └─► citations: one Citation per chunk (truncated snippet)
        └─► SecureRetrievalResult(ALLOW, chunks, citations)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/ragfence/retrieval/service.py` | Create | `RetrievalService` orchestrating guard → filtered search → citations. |
| `src/ragfence/retrieval/result.py` | Create | `SecureRetrievalResult` (ALLOW/DENY) + `Decision` enum. |
| `src/ragfence/retrieval/trace.py` | Create | immutable `RetrievalTrace` (request_id, decision, reasons, chunk_count, latency_ms, store_call_count). |
| `src/ragfence/retrieval/citations.py` | Create | `Citation` assembly (truncation, provenance). |
| `src/ragfence/retrieval/__init__.py` | Modify | export service surface. |
| `src/ragfence/core/models.py` | Modify | extend `Citation` (+`source`, `checksum`, `score`). |
| `tests/support/vector_store.py` | Modify | add counting `VectorStore` double recording `search` calls. |
| `tests/test_secure_retrieval.py` | Create | unit tests (deny/allow/spoof/trace/citations). |
| `tests/integration/test_retrieval_db.py` | Create | DB-gated only-allowed-rows test (`@pytest.mark.db`). |

## Interfaces / Contracts

```python
# retrieval/result.py
class RetrievalDecision(str, Enum): ALLOW = "allow"; DENY = "deny"
@dataclass(frozen=True)
class SecureRetrievalResult:
    decision: RetrievalDecision
    reasons: list[str]
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    trace: RetrievalTrace

# retrieval/service.py
class RetrievalService:
    def __init__(self, *, store: VectorStore,
                 load_row: RowLoader, policy: Callable[[UUID], DocumentPolicy],
                 decide_fn: Callable[[DocumentPolicy, AuthorizationContext], PolicyDecision] = decide):
        ...
    def retrieve(self, request: RetrievalRequest) -> SecureRetrievalResult: ...

# vector_store counting double (tests/support)
class CountingVectorStore:  # conforms to VectorStore protocol
    search_calls: int
    last_predicate: SQL | None
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | DENY = zero store calls (escalation, cross-dept) | counting double asserts `search_calls == 0`; RED first (guard must precede search). |
| Unit | same-dept ALLOW returns ≤ top_k chunks; none outside predicate | seeded `InMemoryVectorStore`; assert predicate passed + top_k honored. |
| Unit | metadata spoofing no-op | modified JSONB metadata → unchanged result; predicate never references `metadata`. |
| Unit | citations provenance + truncation | each citation has title/source/checksum/chunk_index/score; snippet < full content. |
| Unit | trace | request_id, decision, reasons, chunk count, latency, store_call_count; no secret/doc. |
| Integration (DB) | only-allowed rows; zero leakage | `@pytest.mark.db` + `migrated_schema` seed; cross-tenant/dept/deleted/non-ready excluded. |

**TDD order**: counting double + DENY-zero-call RED → ALLOW filtered search → citations → trace → spoof no-op → DB-gated.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The security boundary is the ACL predicate and guard ordering, covered by unit + DB tests above.

## Migration / Rollout

No migration required. `Citation` extension is backward-compatible (new optional/defaulted fields). New files only; revert = delete `retrieval/` additions and tests.

## Open Questions

- [ ] `domain-models` contract change: extending `Citation` with `source`/`checksum`/`score` conflicts with proposal's "consumes unchanged" — confirm scope expansion is accepted (spec req 4 requires it).
- [ ] Confirm `RetrievedChunk` stays unchanged (source/checksum resolved at citation time from the document row, not stored on chunk).
