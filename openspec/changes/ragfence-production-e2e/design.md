# Design: Production Evaluation Path

## Architecture
`ragfence init --up` owns local bootstrap: create config, start the bundled compose DB, wait for readiness, run Alembic, and idempotently seed the deterministic Acme/Globex corpus with fake 1536-dimension embeddings.

The reference adapter receives an `EvaluationCase` request, resolves its principal through the DB-backed directory, invokes `RetrievalService` with `DbVectorStore`, and produces deterministic answer text only from returned chunks. It never substitutes a static blocked result.

## Evaluation contract
- Cases are declarative actor/document/expected-result controls.
- Required positive controls are `must_allow`; required negative controls are `must_block`.
- The matrix owns stable control identifiers plus actor/tenant/document selection, prompt, category, identity/retrieval-evidence requirements, and gate-required status. It does not own execution, target capability detection, score calculation, or `EvaluationGate`; those remain separate vertical slices.
- Case statuses distinguish PASS, FAIL, INCONCLUSIVE, and SKIPPED. Missing actor representation, unavailable target capability, target errors, and absent required control coverage are INCONCLUSIVE; these runs cannot pass a score threshold.
- The score combines security and utility only from executed required controls.

## External identity
`generic_http` represents identity only through an explicit configuration strategy. Header templates can interpolate a constrained allowlist of actor fields. The adapter records whether identity was represented. A case requiring identity is INCONCLUSIVE when no strategy is configured; raw authorization metadata is never implicitly trusted or transmitted.

## Test strategy
Vertical TDD slices cover the fixture, DB reference adapter, CLI bootstrap/output, external identity mapping, scoring semantics, and a Docker-backed end-to-end matrix. CI starts pgvector before pytest and treats DB failures as failures.
