# Proposal: Acme Corp Synthetic Dataset (Phase 3)

## Intent

Build the deterministic, fully synthetic Acme Corp corpus (IMPLEMENTATION_PLAN Phase 3) that later security phases depend on. Without fixed ground truth, attack-engine verdicts (P7) and leakage detection are not reproducible. The dataset is the correctness anchor for Phase 4.

## Scope

### In Scope

- `src/ragfence/datasets/`: Acme Corp org model (1 tenant; departments `engineering`/`hr`/`finance`/`legal`/`executive`; users per department with `Classification`; groups `executives`, `finance-leads`; `user_groups`).
- Synthetic documents per department (design docs, HR policies, payroll, contracts, strategy) with `title`/`source`/`checksum`/`classification`/`status` and `DocumentACL`: department scoping + explicit allowlists where meaningful (e.g. CFO payroll doc with executive-group allowlist).
- Deterministic generation: seeded RNG, stable IDs (fixed/seeded UUIDs), stable SHA-256 checksums; reproducible across runs/machines.
- Two consumption paths: (a) in-memory Pydantic/dataclass objects for future eval phases; (b) loader seeding the storage schema via SQLAlchemy session.
- TDD tests proving security semantics: engineering DENY on finance/payroll/CFO.pdf; same-department ALLOW; group allowlist grant; classification escalation DENY; deterministic regeneration.

### Out of Scope

Retrieval (P5), attack engine (P7), evaluation runner (P8), CLI wiring, embeddings/chunking; `globex_corp` and FakeEmbeddingProvider deferred to keep one reviewable slice.

## Capabilities

Contract for sdd-spec. Existing specs (`project-bootstrap`, `domain-models`, `policy-engine`, `storage-schema`) are unchanged.

### New Capabilities

- `synthetic-dataset`: deterministic Acme Corp corpus — org model, documents + ACLs, reproducibility contract, in-memory + DB loader paths.

### Modified Capabilities

None — dataset consumes `domain-models` / `storage-schema` contracts without altering them.

## Approach

- One package `src/ragfence/datasets/`: `org.py`, `documents.py`, `checksums.py`, `loader.py` (idempotent SQLAlchemy seeding), driven by one seed constant.
- Stable IDs via fixed UUID constants or UUID5(seed); content from seeded RNG so checksums stay stable.
- TDD RED-GREEN-REFACTOR: security-semantics tests against in-memory objects first; DB loader tests DB-gated (skip without DB).
- Delivery: one review slice within the 400-line budget; auto-chain splits if needed.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ragfence/datasets/` | New | Org model, corpus, checksums, loader |
| `tests/` (dataset tests) | New | Security semantics + determinism tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Determinism drift across Python/OS | Med | Seeded RNG + fixed UUIDs; regeneration test asserts identical output |
| Loader violates unique constraints | Med | Idempotent upsert tested in DB-gated test |
| Slice exceeds 400-line budget | Med | Keep corpus concise; auto-chain into 2 slices |
| CFO.pdf classification conflict | Low | Resolve in specs: `confidential` (PRD §2.1) vs `restricted` (launch scope) |

## Rollback Plan

All-new files, no schema/migration changes. Revert = delete `src/ragfence/datasets/` and dataset tests; nothing deployed, no DB impact.

## Dependencies

- Phase 1 `domain-models` (`Classification`, `DocumentACL`, `DocumentPolicy`, `AuthorizationContext`) and Phase 2 `storage-schema` ORM + repositories.
- Python 3.14.5, venv+pip, pytest. No API keys, no network.

## Success Criteria

- [ ] `python -m pytest` green without DB; determinism test passes twice.
- [ ] Security semantics tests pass: cross-dept DENY, same-dept ALLOW, group allowlist grant, escalation DENY.
- [ ] DB-gated loader test seeds idempotently with a reachable PostgreSQL.
- [ ] Change lands as one reviewable slice near the 400-line budget.
