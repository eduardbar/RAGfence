# Proposal: Generic HTTP Adapter (Phase 9)

## Intent

Implement the Phase 9 `GenericHTTPAdapter`, the only component that communicates with an external RAG system. It will adapt configurable HTTP retrieval and generation endpoints to the existing `RAGAdapter` protocol so the Phase 8 evaluation engine can run security scenarios against an external target without coupling the evaluator to that target's framework.

## Scope

### In scope

- `GenericHTTPAdapter` implementing `retrieve`, `answer`, and `is_healthy` from `src/ragfence/core/protocols.py`.
- Typed configuration for `[adapters.generic_http]`, including `base_url`, `retrieve_path`, optional `answer_path`, optional health path, timeout, retry count/backoff, and static bearer authentication.
- POST request mapping from `RetrievalRequest` to `{question, top_k}` and answer requests to `{question, context}`.
- Strict Pydantic parsing of target responses into `RetrievedChunk` values and answer strings; malformed, non-JSON, missing-field, and type-invalid responses fail closed.
- Timeout handling and bounded retry/backoff for health checks, with deterministic behavior suitable for CI.
- `ragfence adapter check generic_http` and `ragfence test --adapter generic_http --base-url ...` integration through the existing CLI seams and report/evidence flow.
- FastAPI-stub tests covering happy paths and documented failure paths.

### Out of scope

- Changes to `RAGAdapter`, domain models, evaluation scoring, persistence schema, or authorization semantics.
- Provider-specific adapters, OAuth/OIDC, dynamic token refresh, arbitrary header templating, or request middleware/plugin systems.
- Logging request/response bodies, bearer tokens, raw authorization headers, or unrestricted target document content.
- Production implementation in this artifact-only change; this change contains OpenSpec artifacts only.

## Dependencies and compatibility

This change depends on Phase 6 CLI/configuration and Phase 8 evaluation/reporting. It preserves the existing `RetrievalRequest`, `RetrievedChunk`, `EvaluationEngine`, and `EvaluationReport` contracts. Runtime failures are represented as adapter errors for the evaluation engine to record as bounded evidence; the adapter never converts malformed data into an apparently valid result.

## Success criteria

- A local FastAPI stub can receive a retrieval request, return strict chunk JSON, and be consumed as `RetrievedChunk[]`.
- An optional answer endpoint returns a strict answer string and can be skipped when `answer_path` is absent.
- Non-JSON responses, missing/invalid fields, timeouts, and exhausted retries produce explicit failures and never fabricate chunks or answers.
- `is_healthy()` retries with bounded backoff and returns `False` after the configured budget.
- Bearer authentication is sent only to the configured target and is absent from logs, exception messages, evidence, and reports.
- `ragfence adapter check generic_http` validates config/reachability, and `ragfence test --adapter generic_http --base-url <stub>` produces the existing report artifact and evidence.
- All implementation work can be validated with focused FastAPI-stub tests plus the existing suite.
