# auth-context

## Requirements

### Requirement: Pre-Authenticated Principal Only

The builder MUST consume a pre-authenticated principal and MUST NOT perform authentication (no password verification or credential exchange). Identity resolution MUST produce a server-side identity record from a synthetic Acme identity or an API-token registry lookup.

#### Scenario: Builder never authenticates

- GIVEN a pre-authenticated principal (Acme user identity or registered API token)
- WHEN `build_authorization_context(principal)` is called
- THEN no credential verification occurs
- AND the principal resolves to a server-side identity record

### Requirement: Server-Side Context Derivation

`build_authorization_context` MUST derive `tenant_id`, `department_id`, `classification`, `allowed_user_ids`, and `allowed_group_ids` ONLY from the identity record and `user_groups` membership. Client-supplied tenant/department/classification params MUST NOT influence the context. A valid identity MUST always yield a valid `AuthorizationContext` with `is_authenticated=True`.

#### Scenario: Engineering user from Acme

- GIVEN the Acme dataset and identity `engineering_employee@acme-corp.example`
- WHEN the context is built
- THEN `tenant_id` is the acme-corp tenant UUID, `department_id` is the engineering UUID, and `classification` is internal
- AND `source` is "synthetic" and `allowed_group_ids` reflects `user_groups` membership

#### Scenario: Client params ignored

- GIVEN client-supplied `tenant_id` and `classification` params
- WHEN the context is built from the identity
- THEN the context carries the server-derived values only
- AND the client values never appear in the context

### Requirement: Synthetic Path (DB-Free)

The synthetic path MUST build contexts without a database by reusing the Acme dataset (`AcmeCorpDataset.context_for`), and MUST be deterministic: the same principal MUST always yield the same context.

#### Scenario: Deterministic and DB-free

- GIVEN no reachable database
- WHEN a context is built for an Acme identity twice
- THEN both calls succeed with no I/O
- AND the two contexts are identical

#### Scenario: Unknown email fails closed

- GIVEN an email absent from the Acme user directory
- WHEN the builder resolves it
- THEN `IdentityNotFoundError` is raised
- AND no context is produced

### Requirement: DB-Backed Path

The DB-backed path MUST derive contexts from the `users` and `user_groups` tables via a SQLAlchemy session, using lowercase enum values; DB-dependent tests MUST be gated on a reachable database.

#### Scenario: Groups derived from user_groups

- GIVEN a seeded DB user in the `executives` group
- WHEN the context is built
- THEN `allowed_group_ids` contains the group UUID
- AND `classification` matches the user row's lowercase value

#### Scenario: DB tests gated

- GIVEN no reachable database
- WHEN the test suite runs
- THEN DB path tests are skipped with a clear reason
- AND synthetic path tests still run

### Requirement: Fail-Closed Typed Errors

The builder MUST raise `IdentityNotFoundError` for unknown identities, MUST raise `IdentityInactiveError` for identities with `is_active=false`, and MUST deny soft-deleted user records (the deleted row is filtered from lookup, failing closed with `IdentityNotFoundError`).

#### Scenario: Inactive user

- GIVEN a user record with `is_active=false`
- WHEN the context is built for that identity
- THEN `IdentityInactiveError` is raised
- AND no context is produced

#### Scenario: Soft-deleted user denied

- GIVEN a user record with `deleted_at` set
- WHEN the context is built for that identity
- THEN the builder fails closed with `IdentityNotFoundError`
- AND no context is produced

### Requirement: API-Token Registry (In-Memory)

The `api_token` path MUST resolve tokens through an in-memory server-side registry mapping token to user key (MVP; DB-backed token store is a future change). Registered tokens MUST yield a context with `source="api_token"`; unknown tokens MUST raise `IdentityNotFoundError`.

#### Scenario: Registered token resolves

- GIVEN a token registered in the in-memory registry
- WHEN the context is built from that token
- THEN the context derives from the mapped user record
- AND `source` is "api_token"

#### Scenario: Unknown token fails closed

- GIVEN a token absent from the registry
- WHEN the context is built from that token
- THEN `IdentityNotFoundError` is raised

### Requirement: Contract Stability

The auth-context capability MUST NOT change the `AuthorizationContext` model contract (fields, `source` literal, `extra="forbid"`) or the policy-engine decision contract; downstream denial remains the policy engine's responsibility.

#### Scenario: Downstream denial delegated (reference)

- GIVEN a valid engineering, internal context from the builder
- WHEN the CFO.pdf policy (finance, confidential) is evaluated by the policy engine
- THEN the context constructs successfully
- AND denial is produced by the policy-engine decision, per the policy-engine spec
