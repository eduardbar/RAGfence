# Spec: Generic HTTP Adapter

## Requirements

### Requirement: Adapter implements the canonical RAGAdapter contract

The system MUST provide a `GenericHTTPAdapter` with `name`, `retrieve(request)`, `answer(request, chunks)`, and `is_healthy()` matching `src/ragfence/core/protocols.py`. The adapter MUST be the only external HTTP boundary; callers MUST continue using canonical core models.

#### Scenario: Retrieve maps a valid target response

- GIVEN a configured base URL and `retrieve_path`
- AND the FastAPI target accepts `POST` JSON `{\"question\": \"What is the policy?\", \"top_k\": 3}`
- AND the target returns `200` with a JSON object containing a valid `chunks` array
- WHEN `retrieve` receives a `RetrievalRequest` with query `What is the policy?` and `top_k=3`
- THEN it returns a list of `RetrievedChunk` instances
- AND each returned model contains validated UUIDs, title, index, content, score, and metadata
- AND no target-specific response object escapes the adapter boundary

#### Scenario: Answer maps a valid target response

- GIVEN `answer_path` is configured
- AND the target accepts `POST` JSON containing the request question and serialized chunk context
- AND the target returns `200` with `{\"answer\": \"The policy requires approval.\"}`
- WHEN `answer` is called with a request and retrieved chunks
- THEN it returns the answer string exactly
- AND it does not expose transport details to the caller

#### Scenario: Answer endpoint is optional

- GIVEN `answer_path` is absent
- WHEN `answer` is requested
- THEN the adapter raises a typed unsupported-operation error
- AND retrieval remains usable for retrieval-only scenarios

### Requirement: Configuration is typed and explicit

The system MUST load `[adapters.generic_http]` with `base_url`, `retrieve_path`, optional `answer_path`, health path, finite timeout, bounded health retries/backoff, and optional static bearer settings. Paths MUST be relative and URLs MUST be valid HTTP(S) URLs. Invalid or missing required configuration MUST be a configuration error before network I/O.

#### Scenario: Configuration loads from TOML

- GIVEN a TOML file with `[adapters.generic_http]`, `base_url`, and `retrieve_path`
- WHEN the CLI loads configuration for `generic_http`
- THEN it produces a typed adapter configuration
- AND omitted optional answer/auth settings remain explicitly disabled
- AND timeout and retry values have finite validated defaults

#### Scenario: Invalid configuration fails closed

- GIVEN a generic HTTP configuration with a missing base URL, absolute endpoint path, non-positive timeout, or negative retry count
- WHEN configuration validation runs
- THEN it raises a configuration error
- AND no HTTP request is attempted

### Requirement: Responses are parsed strictly with Pydantic

The system MUST validate retrieve and answer bodies with strict Pydantic response models before mapping them to domain models. Non-JSON bodies, non-2xx status codes, missing required fields, null required fields, wrong types, malformed UUIDs, and invalid chunk items MUST raise a typed adapter error and MUST NOT return partial success.

#### Scenario: Non-JSON retrieve response

- GIVEN the target returns a non-2xx or 2xx body that is not JSON
- WHEN `retrieve` parses the response
- THEN it raises an adapter parse/transport error
- AND the error identifies the operation without including authorization values or the raw body

#### Scenario: Missing retrieve field

- GIVEN the target returns JSON with a `chunks` item missing `document_id` or `content`
- WHEN `retrieve` validates the body
- THEN it raises a strict validation error
- AND it returns no chunks
- AND the evaluation engine can record the case as errored with bounded evidence

#### Scenario: Invalid answer field

- GIVEN the target returns JSON with a missing, null, or non-string `answer`
- WHEN `answer` validates the body
- THEN it raises a strict validation error
- AND it does not coerce the value or return an empty answer

### Requirement: Timeouts and health retries are bounded

Every external request MUST use a finite timeout. `is_healthy()` MUST retry transient connection/timeout failures and 5xx responses according to configured bounded exponential backoff, then return `False` after exhaustion. It MUST not retry non-transient 4xx responses.

#### Scenario: Health succeeds after retry

- GIVEN the health endpoint times out on the first attempt and returns `200` on the second
- WHEN `is_healthy()` runs with at least two retries configured
- THEN it performs the minimum required attempts
- AND it waits using the configured backoff between attempts
- AND it returns `True`

#### Scenario: Health exhaustion returns false

- GIVEN the health endpoint remains unreachable or returns retryable 5xx responses
- WHEN the retry budget is exhausted
- THEN `is_healthy()` returns `False`
- AND it does not raise an unbounded retry loop
- AND the CLI can report the adapter as unhealthy

#### Scenario: Retrieve timeout fails the case

- GIVEN the retrieve endpoint exceeds the configured timeout
- WHEN `retrieve` is called
- THEN it raises a typed timeout/adapter error
- AND it does not silently retry the POST
- AND the evaluation engine retains bounded error evidence

### Requirement: Static bearer authentication is secret-safe

When configured, the adapter MUST send a static `Bearer <token>` value using the configured auth header. It MUST NOT log, include in exceptions, persist in evidence, or render the token in reports. It MUST not support arbitrary token interpolation or dynamic credential refresh in this phase.

#### Scenario: Auth header reaches the FastAPI stub

- GIVEN a configured static bearer token and auth header
- WHEN `retrieve` or `answer` sends a request
- THEN the stub receives exactly the configured header value
- AND the domain response is mapped normally

#### Scenario: Secret is absent from diagnostics

- GIVEN a target returns an error while bearer authentication is configured
- WHEN the adapter error is logged or passed to evaluation evidence
- THEN the token and full authorization header are absent
- AND only safe operation/status/error metadata remains

### Requirement: Adapter check and CLI integration use existing contracts

The CLI MUST support `ragfence adapter check generic_http` and external evaluation via `ragfence test --adapter generic_http --base-url <stub>`. Adapter construction MUST use TOML settings with explicit CLI base URL override, and command exit/report semantics MUST remain 0 for success, 1 for below threshold, and 2 for configuration/runtime errors.

#### Scenario: Adapter check succeeds

- GIVEN a valid generic HTTP configuration and a healthy FastAPI stub
- WHEN `ragfence adapter check generic_http` runs
- THEN it invokes `is_healthy()`
- AND prints a non-secret availability result
- AND exits with code 0

#### Scenario: Adapter check fails safely

- GIVEN a missing/invalid configuration or unhealthy target
- WHEN `ragfence adapter check generic_http` runs
- THEN it exits with code 2
- AND it reports a safe actionable error without credentials

#### Scenario: External test produces an evidence report

- GIVEN a healthy FastAPI stub and an evaluation suite
- WHEN `ragfence test --adapter generic_http --base-url <stub>` runs
- THEN evaluation cases invoke the adapter through the existing engine seam
- AND retrieved chunks, answers, target errors, prompts, and verdicts are represented in bounded/redacted evidence
- AND the existing text/JSON report artifact is written
- AND no bearer token appears in stdout, stderr, or the report

### Requirement: FastAPI-stub coverage is mandatory

The implementation MUST include integration tests against a local FastAPI stub for happy retrieval/answer paths, non-JSON responses, missing fields, timeouts, health retry/backoff, auth, adapter check, and CLI external evaluation. Tests MUST be deterministic and must not require an external service or real credential.

#### Scenario: Stub suite covers all adapter failure classes

- GIVEN the local FastAPI stub routes can be configured per test
- WHEN the adapter test suite runs
- THEN it exercises valid mapping, non-JSON, missing fields, timeout, retry exhaustion, and auth redaction
- AND failures are asserted as typed, safe adapter outcomes rather than ignored exceptions
