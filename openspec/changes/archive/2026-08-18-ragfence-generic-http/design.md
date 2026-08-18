# Design: Generic HTTP Adapter

## Technical approach

Add a small HTTP client adapter under `src/ragfence/adapters/` behind the existing `RAGAdapter` protocol. The adapter owns URL construction, HTTP transport, timeout/retry policy, authentication header injection, and strict response decoding. The evaluation layer continues to see only `RetrievalRequest`, `RetrievedChunk[]`, answer strings, and adapter errors.

Use one reusable synchronous client (the project's selected HTTP stack) with an explicit per-request timeout. `base_url` is normalized once; configured paths are joined safely and must remain relative. Requests are JSON POSTs. `retrieve` sends `{question: request.query, top_k: request.top_k}`. `answer` sends `{question: request.query, context: [chunk payloads]}`. A missing `answer_path` is an explicit unsupported-generation condition, allowing retrieval-only scenarios to continue.

## Wire contracts

### Configuration

```toml
[adapters.generic_http]
base_url = "http://localhost:8000"
retrieve_path = "/retrieve"
answer_path = "/chat"             # optional
health_path = "/health"            # optional; defaults to "/health"
timeout_seconds = 10.0
health_retries = 3
health_backoff_seconds = 0.25
auth_header = "Authorization"     # optional header name
auth_token = "..."                 # optional static token; sent as Bearer <token>
```

`auth_token` is a static bearer credential, not a template and not a per-request value. An implementation may support a documented environment override for the token, but configuration precedence must be explicit and the value must never be printed, interpolated into exception text, or put in evidence. Header names are validated and restricted to the configured static header; no arbitrary user-controlled headers are accepted.

### Retrieve response

The target MUST return a JSON object with a `chunks` array. Each item MUST contain all fields needed by the canonical `RetrievedChunk` model: `chunk_id`, `document_id`, `document_title`, `chunk_index`, `content`, `score`, and `metadata`. UUIDs, numeric types, and metadata are validated by Pydantic; extra fields are ignored or stripped before the domain model is returned. A missing field, wrong type, malformed UUID, non-object item, non-JSON body, non-2xx status, or schema mismatch raises a typed adapter parse/transport error.

### Answer response

The answer endpoint MUST return a JSON object with an `answer` string. Empty strings are valid if the target explicitly returns them; missing, null, or non-string values fail strict parsing. A non-2xx, non-JSON, or schema-invalid response raises the same typed error family.

### Health response

`is_healthy()` performs a request to `health_path` (GET by default), treats a 2xx response as healthy, and returns `False` for connection errors, timeouts, non-2xx responses, or malformed health responses if a JSON health contract is configured. It retries only transient transport failures and 5xx responses, with bounded exponential backoff; it does not retry 4xx configuration/auth failures.

## Work units and parallelization

| Work unit | Owns | Depends on | Parallelism |
|---|---|---|---|
| A. Contracts/config | Adapter errors, Pydantic wire models, `[adapters.generic_http]` validation and secret-safe defaults | Existing core models and CLI config | Parallel with B |
| B. HTTP transport/auth | URL joining, POST/GET transport, timeout policy, bearer injection, retry/backoff primitive | A error/config contracts | Parallel with C after A |
| C. Response mapping | Strict retrieve/answer parsing and domain mapping | A wire models | Parallel with B after A |
| D. Adapter behavior | `GenericHTTPAdapter` methods and unsupported-answer semantics | B + C | After B/C |
| E. CLI/evaluation integration | Adapter factory, `adapter check`, external target selection, bounded evidence/report handoff | D + existing Phase 8 seams | After D |
| F. FastAPI stub and integration verification | End-to-end stub tests, error paths, secret redaction, CLI report | D + E | Final integration; test scaffolding may begin after A |

Each unit follows RED → GREEN → REFACTOR. A, B, and C have disjoint ownership and may be developed concurrently after the contracts checkpoint. D is the integration checkpoint; E and F must not bypass it.

## Security and failure handling decisions

1. **Fail closed:** malformed target data is an adapter error, never an empty successful result.
2. **Strict parsing:** Pydantic models validate the complete required shape before conversion to domain models; no permissive field guessing.
3. **Secret hygiene:** bearer values are held only in request headers, redacted from exception strings and logs, and excluded from evaluation evidence. Response content stored as evidence follows existing bounded/redaction rules.
4. **Retry scope:** health checks only; retrieve/answer are not automatically replayed to avoid duplicate target side effects and ambiguous evaluation evidence.
5. **Timeouts:** every external call has a finite timeout. Timeout errors carry endpoint-safe context but not URL credentials or request bodies.
6. **CLI compatibility:** retain current exit semantics (0 success, 1 below threshold, 2 configuration/runtime error) and existing report writer; add only the generic HTTP selection/factory seam.

## Verification strategy

Use a local FastAPI application fixture with `/retrieve`, `/chat`, and `/health` routes. Assert received JSON and authorization behavior, mapped domain models, strict failures for non-JSON/missing fields, finite timeout behavior, health retry count/backoff (using an injectable sleeper/clock), absent answer-path behavior, and no token in captured logs/exceptions/evidence. Run focused adapter tests, CLI command tests with Typer's runner, then the existing suite and lint/type checks during implementation.

## Implementation targets (guidance only)

- `src/ragfence/adapters/generic_http.py` and adapter package exports.
- `src/ragfence/cli/config.py`, `src/ragfence/cli/seams.py`, and `src/ragfence/cli/main.py` only at the integration boundary.
- `tests/test_generic_http_adapter.py`, `tests/test_generic_http_config.py`, `tests/test_generic_http_cli.py`, and a FastAPI stub fixture under `tests/support/`.

These are implementation targets for the later apply phase; this OpenSpec change does not modify them.
