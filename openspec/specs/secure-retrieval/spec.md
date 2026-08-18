# Spec for secure-retrieval

## Requirements

### Requirement: RetrievalService Contract

The system MUST expose a `RetrievalService` with `retrieve(request) -> SecureRetrievalResult`, where `request` carries a `RetrievalRequest` plus an already-built `AuthorizationContext` (via `RetrievalRequest.authorization`). The result MUST be an ALLOW result carrying `RetrievedChunk[]` and `Citation[]`, or a DENY result carrying non-empty `reasons` and empty chunks. A DENY MUST NOT raise an exception.

#### Scenario: Allow returns chunks and citations

- GIVEN a request whose authorization context is ALLOW
- WHEN `retrieve` is invoked
- THEN the result is ALLOW with `RetrievedChunk[]` and `Citation[]` populated

#### Scenario: Deny is a typed result

- GIVEN a request whose authorization context is DENY
- WHEN `retrieve` is invoked
- THEN the result is DENY with non-empty `reasons`
- AND `chunks` is empty and no exception is raised

### Requirement: Authorization Before Retrieval

The service MUST run the guard — row-state rules (active/ready/tenant) and `decide()` rules 4–9 — before any vector-store call. A DENY MUST result in zero vector-store calls, verifiable via a counting store double.

#### Scenario: Engineering user denied on CFO.pdf

- GIVEN an engineering, internal context and the finance, confidential CFO.pdf policy
- WHEN `retrieve` is invoked
- THEN the result is DENY with reasons naming the failing rules
- AND the counting store records zero `search` calls

#### Scenario: Confidential clearance denied on board-plan.pdf

- GIVEN a confidential-clearance finance user not in `executives` and the restricted board-plan.pdf policy
- WHEN `retrieve` is invoked
- THEN the result is DENY (classification escalation)
- AND zero vector-store calls are recorded

### Requirement: Filtered Vector Retrieval

On ALLOW, the service MUST search the vector store with `build_acl_predicate` applied — referencing typed columns only, never the JSONB `metadata` column — and MUST return at most `top_k` `RetrievedChunk` entries.

#### Scenario: Same-department allow retrieves

- GIVEN a finance analyst context (finance, confidential) and the CFO.pdf policy
- WHEN `retrieve` is invoked
- THEN the result is ALLOW and returns chunks for allowed rows
- AND no chunk outside the ACL predicate is returned

#### Scenario: Metadata spoofing is a no-op

- GIVEN a chunk whose JSONB metadata is modified to grant broader access
- WHEN `retrieve` is invoked
- THEN the result is unchanged
- AND no predicate references the metadata column

### Requirement: Citation Provenance

The service MUST yield one `Citation` per `RetrievedChunk`, carrying document `title`, `source`, `checksum`, `chunk_index`, and `score`. The citation `snippet` MUST truncate the chunk content (redaction by default); full content remains available on the `RetrievedChunk` for internal use.

#### Scenario: Provenance fields present

- GIVEN an ALLOW result with retrieved chunks
- WHEN citations are inspected
- THEN each citation has `title`, `source`, `checksum`, `chunk_index`, and `score`
- AND the `snippet` is truncated relative to the full chunk content

### Requirement: Retrieval Trace

The service MUST return a structured `RetrievalTrace` on every result — `request_id`, `decision`, `reasons`, number of chunks returned, and latency — for observability. The trace MUST NOT log full document contents or secrets by default.

#### Scenario: Trace records decision and reasons

- GIVEN a completed `retrieve` call
- WHEN the trace is inspected
- THEN it records `request_id`, `decision`, `reasons`, chunk count, and latency
- AND no full document content or secret appears in the trace

### Requirement: DB-Backed Path

The DB-backed path MUST retrieve over repositories and pgvector using the shared predicate, returning only allowed rows; DB-dependent tests MUST be gated on a reachable database.

#### Scenario: DB path returns only allowed rows

- GIVEN a reachable seeded database with cross-tenant, cross-department, deleted, and non-ready chunks
- WHEN a retrieval runs over the DB-backed path
- THEN only ACL-allowed rows are returned and leakage is zero

#### Scenario: DB tests gated

- GIVEN no reachable database
- WHEN the test suite runs
- THEN DB-path tests are skipped with a clear reason
- AND unit tests still run
