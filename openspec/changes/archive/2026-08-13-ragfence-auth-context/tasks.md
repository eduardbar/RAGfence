# Tasks: Authorization Context Builder (auth-context)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550-650 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (auth core + synthetic) -> PR 2 (DB-backed), stacked to main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Auth core + synthetic path, DB-free | PR 1 | `python -m pytest tests/test_auth_errors.py tests/test_auth_registry.py tests/test_auth_providers.py tests/test_auth_builder.py -q` | `python -c "from ragfence.auth import build_authorization_context, SyntheticIdentityProvider, AcmeDirectory; ctx = build_authorization_context('engineering_employee@acme-corp.example', provider=SyntheticIdentityProvider(), directory=AcmeDirectory()); print(ctx.tenant_id, ctx.source)"` — real synthetic build, no DB | Delete `src/ragfence/auth/{errors,identity,registry,providers,builder}.py`, `__init__.py` re-exports, unit tests |
| 2 | DB-backed path via repositories | PR 2 | `python -m pytest tests/test_repositories.py tests/test_auth_db.py tests/integration/test_auth_db.py -q` | `RAGFENCE_TEST_DATABASE_DSN=postgresql+psycopg://ragfence:ragfence@localhost:5433/ragfence python -m pytest tests/integration/test_auth_db.py -q` — Docker PG reachable | Revert `repositories.py` additions, delete `src/ragfence/auth/db.py` + auth DB tests |

## Work Unit 1 (PR 1): Auth Core + Synthetic Path — base: main

### Phase 1: Foundation
- [x] 1.1 Create `src/ragfence/auth/errors.py` — `IdentityError` base; `IdentityNotFoundError`, `IdentityInactiveError` (R5).
- [x] 1.2 Create `src/ragfence/auth/identity.py` — frozen `AuthenticatedIdentity` (user_id, tenant_id, email, source) + `IdentityProvider` protocol (R1).
- [x] 1.3 Create `src/ragfence/auth/registry.py` — `TokenRegistry` protocol; `InMemoryTokenRegistry` token->email (R6).

### Phase 2: Core Implementation
- [x] 2.1 Create `src/ragfence/auth/providers.py` — `SyntheticIdentityProvider` (membership pre-check; defensive `KeyError` -> `IdentityNotFoundError`), `ApiTokenIdentityProvider` (`source="api_token"`), `AcmeDirectory` via `AcmeCorpDataset.context_for` (R1/R3/R6).
- [x] 2.2 Create `src/ragfence/auth/builder.py` — `IdentityDirectory` protocol; `build_authorization_context(principal, *, provider, directory)` — principal-only signature, client params unreachable (R2).
- [x] 2.3 Update `src/ragfence/auth/__init__.py` — re-export public API, keep `AuthorizationContext` contract untouched (R7).

### Phase 3: Verification (strict TDD — RED before GREEN)
- [x] 3.1 RED `tests/test_auth_errors.py` — unknown -> `IdentityNotFoundError`; inactive -> `IdentityInactiveError`; both catchable as `IdentityError` (R5).
- [x] 3.2 RED `tests/test_auth_providers.py` — engineering user derives acme tenant, engineering dept, internal classification, groups, `source="synthetic"` (R2); two calls identical, no I/O (R3); unknown email fails closed (R3).
- [x] 3.3 RED `tests/test_auth_registry.py` — registered token -> `source="api_token"`; unknown token -> `IdentityNotFoundError`; `FakeTokenRegistry` proves decoupling (R6).
- [x] 3.4 RED `tests/test_auth_builder.py` — builder never authenticates (R1); client tenant/classification params never influence context (R2); fake `IdentityDirectory` (R2).
- [x] 3.5 GREEN implement 1.1-2.3; run `python -m pytest -q` — green, no DB.

## Work Unit 2 (PR 2): DB-Backed Path — base: main (after PR 1)

### Phase 4: Repository Seam
- [x] 4.1 RED `tests/test_repositories.py` — `UserRepository.get_active` tenant-scoped by email/id; `group_ids_for_user` returns `user_groups` ids; unknown email -> None (R4).
- [x] 4.2 Modify `src/ragfence/db/repositories.py` — add `UserRepository(BaseRepository)` + `group_ids_for_user(session, tenant_id, user_id)` (R4).

### Phase 5: DB Provider + Directory
- [x] 5.1 RED `tests/test_auth_db.py` — fake-session stubs: `is_active=false` -> `IdentityInactiveError`; unknown -> `IdentityNotFoundError`; groups derived from stubs (R4/R5).
- [x] 5.2 Create `src/ragfence/auth/db.py` — `DbIdentityProvider(session, tenant_id)` (tenant-scoped, Acme constant, `is_active` check) + `DbDirectory` via repositories, lowercase enum classification (R4/R5).

### Phase 6: DB-Gated Integration
- [x] 6.1 RED `tests/integration/test_auth_db.py` — gated skip without `RAGFENCE_TEST_DATABASE_DSN`; seeded executives user -> `allowed_group_ids` + lowercase classification (R4).
- [x] 6.2 Same file — seeded `is_active=false` user -> `IdentityInactiveError`; defensive soft-delete: `active_filters` excludes row -> `IdentityNotFoundError`, no schema change (R5).
- [x] 6.3 GREEN implement 4.2 + 5.2; run gated suite with Docker PG (`RAGFENCE_TEST_DATABASE_DSN=postgresql+psycopg://ragfence:ragfence@localhost:5433/ragfence python -m pytest tests/integration/test_auth_db.py -q`); full `python -m pytest -q` green.

## Commit Units (work-unit-commits)

Tests ship in the same commit as the behavior they verify (RED->GREEN per unit), conventional commits: PR 1 — `feat(auth): error types` -> `feat(auth): identity provider protocol + synthetic path` -> `feat(auth): token registry + api_token provider` -> `feat(auth): context builder` -> `feat(auth): re-export public API`; PR 2 — `feat(db): UserRepository + group_ids_for_user` -> `feat(auth): DB-backed identity provider/directory` -> `test(auth): DB-gated integration`.

## PR Boundaries (chained-pr, stacked-to-main)

- PR 1: start = current main; finish = synthetic builder + unit tests green; rollback = delete auth modules + tests.
- PR 2: start = PR 1 merged to main; finish = DB path + gated tests green; rollback = revert `repositories.py` + delete `db.py` + DB tests.
- Each PR body: start state, finish state, dependency diagram `PR1 -> PR2 -> main` with current PR marked, verification commands, out-of-scope (OIDC, multi-tenant wiring, token DB store).

## Threat Matrix

N/A per design (no routing, shell, subprocess, VCS/PR automation, executable-file, or process-integration boundary; in-memory registry is data, not process integration). No threat RED tests required.
