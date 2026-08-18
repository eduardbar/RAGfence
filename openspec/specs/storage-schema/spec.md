# storage-schema

## Requirements

### Requirement: ORM Models for All Tables

The system MUST define SQLAlchemy 2.x ORM models mapping the 13 BACKEND_SCHEMA tables — `tenants`, `users`, `departments`, `groups`, `user_groups`, `documents`, `document_acl`, `document_chunks`, `evaluation_suites`, `evaluation_cases`, `evaluation_runs`, `evaluation_results`, `security_findings` — with matching column names, types, constraints, and relationships. Enum columns MUST use the Postgres enum types (`classification`, `document_status`, `finding_severity`, `run_status`, `scenario_outcome`).

#### Scenario: Metadata matches schema doc

- GIVEN the ORM models
- WHEN each table's columns are introspected
- THEN names, types, nullability, and defaults match `docs/BACKEND_SCHEMA.md`
- AND `documents` has `deleted_at timestamptz NULL`

### Requirement: Alembic Migration Chain

The system MUST provide an Alembic chain (0001 base, 0002 enums, 0003 tables, 0004 indexes) that applies `upgrade head` idempotently from an empty database.

#### Scenario: Fresh and repeat migration

- GIVEN an empty PostgreSQL database
- WHEN `alembic upgrade head` is run twice
- THEN the first run creates all tables and enums
- AND the second run is a no-op

### Requirement: Vector and Index Defaults

`document_chunks.embedding` MUST be `vector(1536)` by default, with an HNSW index using `vector_cosine_ops`; GIN indexes MUST exist on `document_acl.allowed_user_ids` and `document_acl.allowed_group_ids`.

#### Scenario: Indexes present after upgrade

- GIVEN a migrated database
- WHEN the index catalog is queried
- THEN the HNSW and both GIN indexes exist

### Requirement: Normalized ACL vs JSONB Metadata

Access-relevant fields (`tenant_id`, `department_id`, `classification`, ACL ids) MUST be normalized typed columns; the JSONB `metadata` column MUST NOT be consulted for access decisions.

#### Scenario: Metadata spoofing has no effect

- GIVEN a chunk whose JSONB metadata is modified
- WHEN the access predicate is evaluated
- THEN the decision is unchanged
- AND no predicate references the metadata column

### Requirement: Soft Delete Semantics

Every table with `deleted_at` MUST treat `deleted_at IS NULL` as active; repositories MUST filter soft-deleted rows from all read queries, and deleted rows MUST remain in storage for audit.

#### Scenario: Deleted rows excluded

- GIVEN a document with `deleted_at` set
- WHEN the repository lists documents
- THEN the deleted document is absent from results

### Requirement: Repositories

The system MUST provide repository access per table with soft-delete filters and tenant scoping applied to every read query.

#### Scenario: Tenant isolation

- GIVEN two tenants each with documents
- WHEN tenant A's repository queries documents
- THEN only tenant A's active documents are returned

### Requirement: DB-Gated Tests

Integration tests requiring a database MUST be skipped when no database is reachable; unit tests MUST run without Docker.

#### Scenario: Skip without database

- GIVEN no reachable PostgreSQL database
- WHEN `python -m pytest` runs
- THEN DB integration tests are skipped with a clear reason
- AND all unit tests pass

## Decisions

- Embedding dimension default: `vector(1536)`.
- Soft delete: `deleted_at timestamptz NULL`; every query filters `deleted_at IS NULL`.
