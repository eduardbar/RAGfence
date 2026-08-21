# Production E2E Specification

## Requirement R1: Real reference evaluation
The reference adapter MUST resolve persisted fixture identities and execute retrieval through `RetrievalService` and `DbVectorStore`; `_ReferenceTarget` MUST NOT be used in a normal reference evaluation.

### Scenario R1.1: Cross-tenant actor is denied before vector search
- GIVEN a persisted Globex actor and a persisted Acme document
- WHEN the generated cross-tenant control runs against the reference adapter
- THEN the result is denied with `cross_tenant`, returns zero chunks, and makes zero vector searches.

### Scenario R1.2: Authorized actor retrieves content
- GIVEN a persisted Acme actor authorized for an Acme document with an embedding
- WHEN its required positive control runs against the reference adapter
- THEN pgvector search executes and returns at least one authorized chunk.

## Requirement R2: Declarative control matrix
Every evaluation control MUST define actor, tenant, target document, prompt, expected behavior, category, identity requirement, retrieval evidence requirement, and required-for-gate status in one declarative structure.

The default matrix MUST use these stable control identifiers: `same-tenant-authorized`, `same-tenant-no-permission`, `cross-tenant`, `cross-department`, `explicit-allowlist`, `soft-deleted-document`, `public-same-tenant`, and `insufficient-clearance`. `same-tenant-no-permission`, `cross-tenant`, `cross-department`, `soft-deleted-document`, and `insufficient-clearance` are required `must_block` controls. `same-tenant-authorized`, `explicit-allowlist`, and `public-same-tenant` are required `must_allow` controls. `expected_behavior` MUST be a typed enum with members `MUST_ALLOW` and `MUST_BLOCK`. The matrix remains independent of gate scoring and target execution; those behaviors belong to later work units. The production reference path executes ONLY this matrix; the legacy v0.1 attack scenarios stay on the legacy engine path and never execute inside a production reference evaluation.

### Scenario R2.1: Required controls
- GIVEN the default matrix
- WHEN controls are generated
- THEN it includes same-tenant allow, same-tenant deny, cross-tenant deny, cross-department deny, explicit-allowlist allow, soft-delete deny, public same-tenant allow, and clearance deny.

### Scenario R2.2: Controls are self-describing and deterministic
- GIVEN the default matrix is requested twice with the same fixture seed
- WHEN each control is inspected
- THEN stable ordering and identifiers are equal
- AND every control has a non-empty actor, actor tenant, target document, prompt, category, identity requirement, retrieval-evidence requirement, and required-for-gate value
- AND required positive and negative coverage is represented directly by `expected_behavior`, not inferred from scenario-specific maps.

### Scenario R2.3: Public content is tenant-wide readable
- GIVEN an authenticated same-tenant user whose clearance covers PUBLIC
- WHEN they retrieve a PUBLIC document outside their department
- THEN authorization allows retrieval without an explicit grant or department match
- AND the DB ACL predicate and the in-memory policy engine enforce the same public-content exception.

## Requirement R3: First-class result and gate states
Case execution MUST expose PASS, FAIL, INCONCLUSIVE, or SKIPPED. A single gate abstraction MUST fail closed for required failures, required inconclusive controls, missing positive/negative coverage, missing identity/retrieval evidence, target errors, or threshold failure.

### Scenario R3.1: Block-all target
- GIVEN a target returning no chunks for every request
- WHEN the matrix runs
- THEN required MUST_ALLOW controls fail and the gate fails.

### Scenario R3.2: Allow-all target
- GIVEN a target returning chunks for every request
- WHEN the matrix runs
- THEN required MUST_BLOCK controls fail and the gate fails.

### Scenario R3.3: Offline production run asserts a single outcome contract
- GIVEN the declarative matrix runs against the local reference adapter with no external provider configured
- WHEN the CLI writes the JSON report
- THEN the outcome is exactly `pass`, the report declares `real_provider_used: false`, and the invocation performs no non-loopback network egress
- AND the legacy generation-skip semantics (`no_real_provider`) do not apply because the matrix contains no generation-stage controls and no provider is consulted.

## Requirement R4: Explicit external identity
An external adapter MUST represent identity only via explicit allowed configuration. Identity-dependent controls without representation MUST be INCONCLUSIVE.

### Scenario R4.1: Header templates
- GIVEN a headers identity strategy with allowed actor placeholders
- WHEN two distinct actors retrieve
- THEN their requests contain distinct configured identity headers without secrets in reports or evidence.

### Scenario R4.2: Missing or invalid identity configuration
- GIVEN an identity-dependent control and no strategy, missing token, or unknown placeholder
- WHEN it runs
- THEN the case is INCONCLUSIVE and the gate fails without leaking a secret.

## Requirement R5: Executable local and CI contract
`ragfence init --up` MUST start, migrate, seed, and embed the reference DB. `ragfence test --output PATH` MUST write the requested report. CI MUST start pgvector and execute critical DB tests without optional skips.

### Scenario R5.1: Clean room CLI
- GIVEN a clean compose volume
- WHEN `ragfence init --up`, `ragfence test`, JSON output, and explicit output run
- THEN all commands use the real reference path and produce deterministic redacted artifacts.
