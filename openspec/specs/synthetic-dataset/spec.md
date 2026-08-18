# synthetic-dataset

## Requirements

### Requirement: Deterministic Org Model

The dataset MUST generate one Acme Corp tenant (`acme-corp`) with departments `engineering`, `hr`, `finance`, `legal`, `executive`; users assigned to departments with `Classification` clearance covering all four tiers (public, internal, confidential, restricted); groups `executives` and `finance-leads`; and `user_groups` membership. All identifiers MUST be fixed stable UUIDs.

#### Scenario: Fixture shape is complete

- GIVEN the org-model generator with the fixed seed
- WHEN it generates the org
- THEN exactly one tenant and five departments exist
- AND users cover every classification tier and map to groups via `user_groups`

#### Scenario: Identifiers are stable

- GIVEN two generation runs with the same seed
- WHEN UUIDs are compared
- THEN every identifier is identical

### Requirement: Synthetic Document Corpus

The dataset MUST generate at least one document per department with `title`, `source`, `checksum`, `classification`, `status`, and a `DocumentACL` per document (department scoping by default; explicit allowlists where meaningful). `checksum` MUST be lowercase SHA-256 hex. `finance/payroll/cfo-payroll-summary.pdf` MUST be `confidential`; `executive/strategy/2026-board-plan.pdf` MUST be `restricted` with access granted solely through the `executives` group allowlist.

#### Scenario: Per-department coverage

- GIVEN the generated corpus
- WHEN documents are listed
- THEN every department has at least one `ready` document with metadata and an ACL

#### Scenario: Key security fixtures exist

- GIVEN the generated corpus
- WHEN the CFO.pdf and board-plan.pdf policies are inspected
- THEN CFO.pdf is `confidential` with finance department scope
- AND board-plan.pdf is `restricted` with `executives` in `allowed_group_ids`

### Requirement: Byte-Identical Regeneration

The dataset MUST be deterministic: the same seed and inputs MUST regenerate byte-identical org model, corpus, and checksums.

#### Scenario: Regeneration equality

- GIVEN the fixed seed
- WHEN generation runs twice in fresh processes
- THEN serialized org, documents, ACLs, and checksums are byte-identical

### Requirement: In-Memory Consumption Path

The dataset MUST expose typed in-memory Python models — reusing core building blocks `Classification`, `DocumentPolicy`, `DocumentACL`, `AuthorizationContext` — usable without a database.

#### Scenario: Corpus usable without a database

- GIVEN the in-memory corpus
- WHEN a `DocumentPolicy` for CFO.pdf and an `AuthorizationContext` for the finance analyst are constructed
- THEN policy evaluation succeeds with no I/O

#### Scenario: Strict typing enforced

- GIVEN a record with an unknown classification or an ACL with extra fields
- WHEN models are constructed
- THEN construction fails with a validation error

### Requirement: DB Loader Path

The dataset MUST provide a loader that seeds the `storage-schema` tables through a SQLAlchemy session, inserting rows that satisfy FK and unique constraints with lowercase enum values (`ready`, `confidential`, `restricted`).

#### Scenario: Seeds schema cleanly

- GIVEN a migrated empty database
- WHEN the loader seeds through a session
- THEN tenant, department, group, user, user_group, document, and document_acl rows are inserted without constraint violations

#### Scenario: Idempotent re-seed

- GIVEN a seeded database
- WHEN the loader runs again
- THEN no duplicates or unique-violation errors occur
- AND row counts are unchanged

### Requirement: Fixture Security Semantics

Fixture policies MUST produce policy-engine outcomes: cross-department and classification DENY, same-department ALLOW, group-allowlist grant, and classification-escalation DENY.

#### Scenario: Engineering user denied on CFO.pdf

- GIVEN an engineering, internal-clearance context
- WHEN the CFO.pdf policy (finance, confidential) is evaluated
- THEN `allowed` is false
- AND `reasons` is non-empty and names the classification rule (the decision engine reports the first failing rule; the department mismatch also applies)

#### Scenario: Same-department allow

- GIVEN a finance analyst context (finance, confidential)
- WHEN the CFO.pdf policy is evaluated
- THEN `allowed` is true

#### Scenario: Executives group allowlist grants access

- GIVEN a restricted-clearance user in the `executives` group
- WHEN the board-plan.pdf policy is evaluated
- THEN `allowed` is true

#### Scenario: Confidential clearance denied on board-plan.pdf

- GIVEN a confidential-clearance finance user not in `executives`
- WHEN the board-plan.pdf policy is evaluated
- THEN `allowed` is false
