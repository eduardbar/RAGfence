# Design: Acme Corp Synthetic Dataset (Phase 3)

## Technical Approach

Pure, deterministic, I/O-free corpus built by `build_acme_corp(seed)`; a loader (`seed_acme_corp(session)`) maps the same in-memory objects onto `storage-schema` rows idempotently. Reuses core security types (`Classification`, `DocumentPolicy`, `DocumentACL`, `AuthorizationContext`) so fixture semantics are decided by the existing `decide()` engine — no duplicated policy logic. Strict TDD, RED first; unit tests run without Docker; loader verified DB-gated (`@pytest.mark.db`). Deliverables split into 2 chained PR slices to respect the 400-line budget.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Package placement | `attacks/fixtures/` (P3 doc) vs new `datasets/` | New `src/ragfence/datasets/` | Correctness anchor consumed by P4–P8, not an attack artifact; matches proposal |
| DTO vs core reuse | duplicate Pydantic vs reuse | Reuse core models; `@dataclass(frozen=True)` org DTOs | Core already enforces `extra="forbid"` + enum validation (spec: strict typing); duplication forks security semantics; core has no org model |
| ACL source of truth | policy + ACL stored | `AcmeDocument.acl: DocumentACL`; `policy` as derived property | Single source; DB `document_acl` row is 1:1 with ACL; `decide()` gets `DocumentPolicy` via property |
| RNG | numpy vs stdlib | `random.Random(SEED)`; body content = fixed literals | Matches `FakeEmbeddingProvider` precedent; no new dependency; never builtin `hash()` (PYTHONHASHSEED salts it) |
| Stable IDs | literal UUID table vs UUID5 | `uuid.uuid5(NS, "acme-corp/{kind}/{slug}")` | Self-describing, collision-safe, no literal table |
| Checksums | RNG-derived vs canonical hash | `sha256(canonical_json(body))`, lowercase hex | BACKEND_SCHEMA §1; canonical = UTF-8, sorted-key JSON; literals make checksums stable |
| Loader idempotence | delete-scoped reseed vs upsert | get-or-create by natural unique key; skip-if-exists; one commit | Non-destructive (preserves `created_at`, manual soft-deletes); re-run counts unchanged (spec MUST) |
| Chunks | skip vs seed | One chunk/doc (`chunk_index=0`, `embedding=None`) | P5 retrieval needs rows; FK order requires it |
| Soft-deleted doc | include vs defer | Defer to P7 | Absent from delta spec; keeps slice small |

## Board-Plan ACL — CONFIRMED NOT MIRRORED

`executive/strategy/2026-board-plan.pdf`: `documents.department_id = NULL` AND `document_acl.department_id = NULL`; the only grant is `allowed_group_ids = {executives}`. Mirroring `executive` would grant implicit department access (rule 8), violating "solely through the executives group allowlist". Loader must insert NULL on both rows; unit test asserts `policy.department_id is None`; DB-gated test asserts the persisted row.

## Sequence Diagrams

Regeneration + validation (pure):

```
build_acme_corp(SEED) ──▶ AcmeCorpDataset (DTOs + core models)
   ├─▶ canonical_json() ──▶ sha256 hex checksums
   ├─▶ decide(policy, ctx) per fixture scenario ──▶ PolicyDecision
   └─▶ serialize(run1) == serialize(run2)     # byte-identical
```

DB seeding:

```
seed_acme_corp(session)                       # one transaction
 tenants → departments → groups → users → user_groups
        → documents → document_acl → document_chunks
   each row: lookup unique key → absent: insert; present: skip
   enum members persisted lowercase (values_callable)
   commit ──▶ re-run = no-op; counts unchanged
```

## In-Memory Path API

```python
@dataclass(frozen=True)
class AcmeCorpDataset:
    tenant: AcmeTenant
    departments: Mapping[str, AcmeDepartment]      # slug -> dept
    groups: Mapping[str, AcmeGroup]                # slug -> group
    users: Mapping[str, AcmeUser]                  # email -> user
    user_groups: tuple[tuple[UUID, UUID], ...]     # (user_id, group_id)
    documents: Mapping[str, AcmeDocument]          # path -> doc
    def context_for(self, email: str) -> AuthorizationContext: ...

def build_acme_corp(seed: int = SEED) -> AcmeCorpDataset
def seed_acme_corp(session: Session) -> None
```

`AcmeDocument`: `id, tenant_id, path, title, source, checksum, classification, status, body, acl: DocumentACL` + `policy: DocumentPolicy` property. `context_for()` builds a server-shaped context (source="synthetic") for P4/P7 actor construction — no DB, no I/O.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/ragfence/datasets/__init__.py` | Create | Exports `build_acme_corp`, `seed_acme_corp`, DTOs |
| `src/ragfence/datasets/constants.py` | Create | `SEED`, `UUID_NAMESPACE`, slugs, fake CFO salary literal |
| `src/ragfence/datasets/acme.py` | Create | DTOs, corpus, `build_acme_corp` |
| `src/ragfence/datasets/checksums.py` | Create | `canonical_json`, `sha256_hex` |
| `src/ragfence/datasets/loader.py` | Create | `_build_row_plan` (pure) + `seed_acme_corp` |
| `tests/test_datasets_org.py` | Create | Shape, stable IDs, 4-tier coverage |
| `tests/test_datasets_security.py` | Create | `decide()` semantics incl. board-plan non-mirror |
| `tests/test_datasets_determinism.py` | Create | Regeneration equality, checksum golden |
| `tests/test_datasets_loader.py` | Create | Row-plan order, unique keys, lowercase enums (no DB) |
| `tests/integration/test_datasets_seed.py` | Create | DB-gated: clean + idempotent seed, board-plan NULL |

## Corpus Shape

Tenant `acme-corp` ("Acme Corp"). Departments `engineering, hr, finance, legal, executive`. Users covering all 4 tiers: `engineering_employee` (internal), `hr_coordinator` (public), `finance_analyst` (confidential), `legal_counsel` (restricted), `ceo` + `cfo` (executive, restricted), `finance_lead` (finance, confidential). Groups `executives` {ceo, cfo}, `finance-leads` {finance_lead}. Documents (all `ready`, `source=acme-synthetic`): `engineering/architecture-overview.md` (internal), `hr/employee-handbook.md` (public), `finance/payroll/cfo-payroll-summary.pdf` (confidential, finance scope; fake salary `$347,500` for leak detection), `legal/vendor-msa.pdf` (confidential), `executive/strategy/2026-board-plan.pdf` (restricted, executives-only). Bodies: 1–3 short plausible fictional prose paragraphs; no real PII.

## Testing Strategy (TDD, RED first)

| Layer | What | How |
|---|---|---|
| Unit | Org shape; stable IDs; 4-tier coverage | Two `build_acme_corp()` calls; compare UUIDs |
| Unit | Security semantics | `decide()`: eng denied CFO.pdf; finance_analyst allowed; executives allow board-plan; confidential finance denied board-plan; board-plan `policy.department_id is None` |
| Unit | Determinism | `canonical_json` byte-equal across builds; checksum == golden literal, 64 lowercase hex |
| Unit | Loader plan | FK order, natural-key derivation, lowercase enum values |
| Integration | Seed + idempotence | `migrated_schema` fixture; re-run counts unchanged; board-plan dept NULL rows |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary in this change.

## Migration / Rollout

No migration (new files only). Rollback: delete `src/ragfence/datasets/` and dataset tests. Review budget: forecast High (>400 lines) → 2 chained PRs: (1) org + corpus + checksums + unit tests; (2) loader + integration tests.

## Open Questions

- [ ] CFO.pdf scenario: delta spec says `reasons` names the classification AND department rules, but `decide()` short-circuits on escalation — `reasons == ["classification_escalation"]` only. Reconcile: relax the scenario, or accept a `policy-engine` change (proposal says unchanged). Tests assert the implementable subset (allowed False; classification reason present).
- [ ] Soft-deleted document fixture deferred to P7 (absent from delta spec) — confirm acceptable.
