# Proposal: Authorization Context Builder (Phase 4)

## Intent

Close the gap between authenticated identity and enforceable access decisions (IMPLEMENTATION_PLAN Phase 4). `auth/` is currently a stub; contexts exist only as fixtures (`AcmeCorpDataset.context_for`). Retrieval (P5) needs a server-side builder that derives `AuthorizationContext` from the authenticated backend identity — never from client-supplied params — keeping authentication (who) and authorization (what) separate.

## Scope

### In Scope

- `auth/` package: identity resolution from an authenticated principal — synthetic demo identities (Acme users) and an API-token lookup path; OIDC as interface/backlog only.
- `build_authorization_context(identity) -> AuthorizationContext`: tenant_id, department_id, classification, allowed_group_ids derived server-side from the identity record (in-memory for synthetic; `users` + `user_groups` via storage layer for DB).
- Authentication vs authorization separation; `source` provenance recorded (`synthetic` | `api_token`).
- Typed deny/error behavior for unknown, inactive identities.
- TDD tests: derivation; unknown/inactive denial; client-supplied params ignored; synthetic path DB-free; DB path DB-gated.

### Out of Scope

Real OIDC provider, password auth/tokens, retrieval service (P5), API endpoints, CLI wiring.

## Capabilities

### New Capabilities

- `auth-context`: identity resolution + server-side `AuthorizationContext` derivation; deny-on-unknown; synthetic and DB-backed paths.

### Modified Capabilities

None — consumes `domain-models`, `synthetic-dataset`, `storage-schema` contracts unchanged.

## Approach

- `auth/identity.py`: `IdentityProvider` protocol + `AuthenticatedIdentity` (user_id, tenant_id, email, source).
- `auth/providers.py`: `SyntheticIdentityProvider` (wraps `build_acme_corp().context_for`) and `ApiTokenIdentityProvider` (server-side token registry).
- `auth/context.py`: `build_authorization_context` — accepts identity only, derives from directory, raises typed errors for unknown/inactive (fail closed).
- `auth/db.py`: DB-backed lookup over `users`/`user_groups` via repositories, `is_active` check.
- TDD RED-GREEN-REFACTOR; DB tests gated by `RAGFENCE_TEST_DATABASE_DSN`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ragfence/auth/` | New | identity, providers, context builder, db path |
| `tests/` (auth tests) | New | derivation, deny, spoofing, gated DB tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| OIDC overbuild | Med | Interface + backlog only, no provider |
| Client-param spoofing | Med | Builder accepts identity only; tests assert params ignored |
| Inactive/deleted semantics drift | Med | Typed errors + explicit tests |

## Rollback Plan

New files only; no schema or migration changes. Revert = delete `src/ragfence/auth/` additions and auth tests; no deployed state affected.

## Dependencies

- Phases 1–3: `domain-models` (`AuthorizationContext`), `synthetic-dataset` (`context_for`), `storage-schema` (`users`/`user_groups` for DB path).
- Python 3.14.5, venv+pip, pytest; PostgreSQL reachable for DB-gated tests.

## Success Criteria

- [ ] `python -m pytest` green without DB; synthetic derivation works.
- [ ] Unknown/inactive identities raise typed errors (fail closed).
- [ ] Client-supplied tenant/department/role params never influence the context.
- [ ] DB-gated test builds context from seeded users with a reachable PostgreSQL.
- [ ] Delivery within the 400-line review budget; auto-chain if exceeded.

## Proposal question round

Assumptions for user review: (1) builder consumes an already-authenticated principal — password verification and login endpoints stay out of scope; (2) deny behavior is a typed exception (fail closed), not a denied context; (3) `api_token` path uses an in-memory server-side registry for MVP, DB-backed later. Correct or run a second round on request.
