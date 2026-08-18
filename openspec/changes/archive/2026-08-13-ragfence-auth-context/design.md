# Design: Authorization Context Builder (auth-context)

## Technical Approach

Two-layer boundary, mirroring TRD §5.4: authentication resolves a pre-authenticated principal into an `AuthenticatedIdentity` (who); authorization derives the `AuthorizationContext` from a server-side directory (what may they see). `build_authorization_context(principal, *, provider, directory)` orchestrates both. Synthetic vs DB-backed path selection is dependency injection at the call site — same seam pattern as `guard_retrieval`'s injected `load_row`/`retrieve` callables. Reuses `AuthorizationContext` (contract unchanged), `AcmeCorpDataset.context_for` (synthetic path), and `users` + `user_groups` via repositories (DB path). Unknown/inactive identities raise typed errors: fail closed before any retrieval.

## Architecture Decisions

### ADR: Authentication/authorization separation boundary (spec: Pre-Authenticated Principal Only)
| Option | Tradeoff | Decision |
|---|---|---|
| Single function: principal → context in one step | Fewer modules, but couples credential-side with directory; hard to audit/swap (OIDC later) | Rejected |
| Separate `IdentityProvider` (who) + `IdentityDirectory` (what) protocols; builder orchestrates | Two seams; each boundary independently testable and swapable | **Adopted** |

### ADR: Fail-closed exceptions vs denied context
| Option | Tradeoff | Decision |
|---|---|---|
| Return context with `is_authenticated=False` | Callers must remember to check; a forgotten check lets a denied ctx reach retrieval | Rejected |
| Raise `IdentityNotFoundError` / `IdentityInactiveError` | Aborts pipeline before `guard_retrieval`; caller maps exception to denial | **Adopted** (proposal assumption 2) |

### ADR: In-memory token registry (MVP)
| Option | Tradeoff | Decision |
|---|---|---|
| `tokens` table in storage schema | Schema + migration change; DB dependency for a demo path | Rejected |
| `InMemoryTokenRegistry` behind `TokenRegistry` protocol (token → user key) | Zero schema change; swappable for DB-backed store later | **Adopted** (proposal assumption 3) |

### ADR: Synthetic path reuses Acme dataset
| Option | Tradeoff | Decision |
|---|---|---|
| Re-implement derivation from `USER_SPECS` | Duplicates fixture truth; drift risk | Rejected |
| Delegate to `dataset.context_for(email)`; provider pre-checks membership, defensive `KeyError` → `IdentityNotFoundError` | Deterministic, DB-free, single source of truth | **Adopted** |

### ADR: DB path group derivation via `user_groups` join
| Option | Tradeoff | Decision |
|---|---|---|
| Bespoke SQL join inside `auth/db.py` | Bypasses repository row-state semantics (storage-schema: tenant-scoped reads) | Rejected |
| `UserRepository` (tenant-scoped) + `group_ids_for_user(session, user_id)`; `is_active` checked by provider → typed `IdentityInactiveError` | Reuses storage layer; group ids from `user_groups` join | **Adopted** |

### ADR: users soft-delete scope (spec scenario "Soft-deleted user denied")
`users` has NO `deleted_at` (BACKEND_SCHEMA §4: `is_active` only). DB path checks `is_active == true` → `IdentityInactiveError`; absent row → `IdentityNotFoundError`. Soft-deleted rows are out of scope for `users` today: soft-delete semantics apply only to tables with `deleted_at` (e.g. `documents`). If `deleted_at` is ever added to `users`, the repository soft-delete filter (`active_filters`) excludes the row → `IdentityNotFoundError` (fail closed), satisfying the scenario defensively. **No storage-schema change needed** — no column, no migration.

## Data Flow

(1) Identity → authentication boundary → builder → context → policy engine:
```
principal (email | token)
  → IdentityProvider.resolve()        [authentication; never verifies credentials]
  → AuthenticatedIdentity(user_id, tenant_id, email, source)
  → build_authorization_context() → IdentityDirectory.lookup()
  → AuthorizationContext(is_authenticated=True, source)
  → guard_retrieval(ctx, policy, ...) [policy engine; contract unchanged]
```

(2) Synthetic vs DB path resolution:
```
            build_authorization_context(principal, provider, directory)
                                │
             ┌──────────────────┴──────────────────┐
  synthetic (no DB)                      DB-backed (session)
  SyntheticIdentityProvider + AcmeDirectory      DbIdentityProvider(session, tenant_id) + DbDirectory(session)
  AcmeCorpDataset.context_for(email)             users (is_active) + user_groups
  source="synthetic"                             source from identity
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/ragfence/auth/errors.py` | Create | `IdentityError` base; `IdentityNotFoundError`, `IdentityInactiveError` |
| `src/ragfence/auth/identity.py` | Create | `AuthenticatedIdentity` + `IdentityProvider` protocol |
| `src/ragfence/auth/registry.py` | Create | `TokenRegistry` protocol + `InMemoryTokenRegistry` |
| `src/ragfence/auth/providers.py` | Create | `SyntheticIdentityProvider`, `ApiTokenIdentityProvider` (composes user resolver, sets `source="api_token"`), `AcmeDirectory` |
| `src/ragfence/auth/builder.py` | Create | `build_authorization_context` + `IdentityDirectory` protocol |
| `src/ragfence/auth/db.py` | Create | `DbIdentityProvider` (tenant-scoped, `is_active` → `IdentityInactiveError`), `DbDirectory` (user + groups) |
| `src/ragfence/auth/__init__.py` | Modify | Re-export public API from stub docstring |
| `src/ragfence/db/repositories.py` | Modify | Add `UserRepository` (get by email/id) + `group_ids_for_user` |
| `tests/test_auth_*.py` | Create | Unit: synthetic derivation, errors, spoofing, registry, fake-session provider |
| `tests/integration/test_auth_db.py` | Create | DB-gated derivation + inactive-user tests |

## Interfaces / Contracts

```python
class IdentityError(Exception): ...
class IdentityNotFoundError(IdentityError): ...
class IdentityInactiveError(IdentityError): ...

class AuthenticatedIdentity:                      # frozen dataclass
    user_id: UUID; tenant_id: UUID; email: str
    source: Literal["synthetic", "oidc", "api_token"]

class IdentityProvider(Protocol):
    def resolve(self, principal: str) -> AuthenticatedIdentity: ...

class IdentityDirectory(Protocol):
    def lookup(self, identity: AuthenticatedIdentity) -> AuthorizationContext: ...

def build_authorization_context(principal: str, *, provider: IdentityProvider,
                                directory: IdentityDirectory) -> AuthorizationContext: ...

class TokenRegistry(Protocol):
    def resolve(self, token: str) -> str | None: ...  # token → user key (email)
```

Client-supplied tenant/department/classification params cannot reach the builder — the signature accepts a principal only.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Synthetic derivation (engineering user: tenant/dept/classification/groups/`source="synthetic"`); determinism (two calls identical); DB-free | Pure, no fixtures |
| Unit | Fail-closed: unknown email → `IdentityNotFoundError`; inactive → `IdentityInactiveError` (fake-session User stubs); error hierarchy catchable as `IdentityError` | errors module |
| Unit | Spoofing: client tenant/classification params never influence context | builder signature + derivation asserts |
| Unit | Token registry: registered token → `source="api_token"`; unknown token → `IdentityNotFoundError`; `FakeTokenRegistry` proves protocol decoupling | registry module |
| Integration (db-gated) | Seeded users → groups from `user_groups`, lowercase classification; `is_active=false` user → `IdentityInactiveError` | `migrated_schema` fixture, `seed_acme_corp` |

TDD order (strict_tdd): RED unit (synthetic derivation → errors → spoofing → registry → fake-session provider) → GREEN → REFACTOR; then RED DB-gated → GREEN. DB tests skip without `RAGFENCE_TEST_DATABASE_DSN`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The token registry is in-memory data, not process/OS integration.

## Migration / Rollout

No migration required. New files only; no schema change; no feature flag (paths selected by injection).

## Open Questions

- [ ] Confirm single-tenant assumption: `DbIdentityProvider` takes `tenant_id` at construction (server-side Acme constant); multi-tenant identity resolution deferred to session/request wiring (future change).
