# Tasks: Secure Retrieval Service (Phase 5)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~550 (source 250 / tests 250 / support 50) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 (stacked to main) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | DENY guard + result/trace types + counting double | PR 1 | `python -m pytest tests/test_secure_retrieval.py -k deny` | N/A — unit, zero I/O | delete `retrieval/result.py`, `retrieval/trace.py`, counting double; no deploy state |
| 2 | ALLOW filtered search + citations + metadata-spoof no-op | PR 2 | `python -m pytest tests/test_secure_retrieval.py` | N/A — InMemory store double | delete `retrieval/service.py` ALLOW branch + `retrieval/citations.py` |
| 3 | DB-backed only-allowed-rows path | PR 3 | `python -m pytest tests/integration/test_retrieval_db.py -m db` | Docker PG on 5434; `RAGFENCE_TEST_DATABASE_DSN` | delete `tests/integration/test_retrieval_db.py`; no migration |

## Phase 1: Foundation — Result & Trace Types (PR 1)

- [x] 1.1 RED: write DENY tests in `tests/test_secure_retrieval.py` — typed result (spec: Deny is a typed result), Engineering-on-CFO.pdf deny, Confidential escalation on board-plan.pdf deny; assert `search_calls == 0` via counting double (spec: zero store calls). `python -m pytest tests/test_secure_retrieval.py -k deny` fails.
- [x] 1.2 Create `src/ragfence/retrieval/result.py`: `RetrievalDecision` enum + frozen `SecureRetrievalResult` (decision, reasons, chunks, citations, trace).
- [x] 1.3 Create `src/ragfence/retrieval/trace.py`: immutable `RetrievalTrace` (request_id, decision, reasons, chunk_count, latency_ms, store_call_count).
- [x] 1.4 Add `CountingVectorStore` double to `tests/support/vector_store.py` (records `search` calls, `last_predicate`).
- [x] 1.5 Create `src/ragfence/retrieval/service.py` DENY path: load row state + `decide()` before any store call; returns typed DENY, zero store calls.
- [x] 1.6 GREEN: pass PR 1 tests. `python -m pytest tests/test_secure_retrieval.py -k deny`.

## Phase 2: Core — ALLOW Path, Citations, Trace (PR 2)

- [x] 2.1 RED: write ALLOW tests — same-department allow retrieves ≤ top_k, no chunk outside predicate (spec: same-department allow); metadata spoofing no-op (spec: no predicate references metadata); citations provenance fields + snippet truncation (spec: Provenance fields present); trace records decision+reasons, no content/secrets (spec: Trace records). `python -m pytest tests/test_secure_retrieval.py` fails.
- [x] 2.2 GREEN: complete `retrieval/service.py` ALLOW branch — call `store.search(embedding, policy_predicate=build_acl_predicate, top_k)`; single predicate, typed columns only.
- [x] 2.3 Create `src/ragfence/retrieval/citations.py`: one `Citation` per chunk (title/source/checksum/chunk_index/score); snippet truncated ~200 chars; full content stays on chunk.
- [x] 2.4 Update `src/ragfence/retrieval/__init__.py` to export service surface.
- [x] 2.5 GREEN: pass full unit suite. `python -m pytest tests/test_secure_retrieval.py`.

## Phase 3: Integration — DB-Backed Path (PR 3)

- [x] 3.1 RED: write `tests/integration/test_retrieval_db.py` `@pytest.mark.db` — seed cross-tenant/dept/deleted/non-ready rows via `migrated_schema`, assert only ACL-allowed rows returned, leakage 0 (spec: DB path returns only allowed rows). Fails/skips without DB.
- [x] 3.2 GREEN: run DB-gated path over repositories + pgvector with shared predicate. `python -m pytest tests/integration/test_retrieval_db.py -m db` (Docker PG 5434).
- [x] 3.3 Verify gating: DB-path tests skip with clear reason when DB unreachable; unit tests still run (spec: DB tests gated).

## Phase 4: Verification & Cleanup

- [x] 4.1 Run full suite + ruff + mypy: `python -m pytest`, `ruff check`, `mypy`.
- [x] 4.2 Confirm no migration, no post-hoc filtering, no JSONB metadata in predicate; commit work units per PR.
