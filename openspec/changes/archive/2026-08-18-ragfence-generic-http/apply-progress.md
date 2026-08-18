# Apply Progress: Generic HTTP Adapter (Phase 9)

## Work Units A–C — Contracts, transport, mapping

- RED → GREEN → REFACTOR completed.
- Typed config validates HTTP(S) URLs, relative paths, finite timeout, bounded retries/backoff, and static auth.
- Strict Pydantic wire mapping validates retrieve/answer responses and fails closed.
- Standard-library transport uses JSON POST/GET, finite timeout, Bearer auth, health-only retry/backoff, and no POST retries.

## Work Unit D — Adapter

- RED → GREEN → REFACTOR completed.
- `GenericHTTPAdapter` implements `RAGAdapter` with retrieve, answer, and health methods.
- Retrieval-only mode raises typed unsupported-operation errors for answer.

## Work Unit E — CLI integration

- RED → GREEN → REFACTOR completed.
- `adapter check generic_http` constructs the configured adapter and returns safe exit 0/2 behavior.
- `ragfence test --adapter generic_http --base-url ...` applies the override, invokes the target, and writes the existing report artifact.
- Reference mode and legacy threshold conversion remain compatible.

## Work Unit F — Stub verification

- RED → GREEN → REFACTOR completed with deterministic stdlib HTTP route doubles because FastAPI/httpx are not project dependencies.
- Covered happy paths, retrieval-only mode, malformed responses, missing fields, timeouts, health retry exhaustion, 4xx no-retry, auth delivery/redaction, and malformed health.

## Verification evidence

- `RAGFENCE_TEST_DATABASE_DSN=...localhost:5434/ragfence uv run pytest -q`: 350 passed, 0 skipped.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run mypy`: passed, 59 source files.
- `uv build`: passed; wheel and source distribution created.
- No deploy, commit, or push performed.
