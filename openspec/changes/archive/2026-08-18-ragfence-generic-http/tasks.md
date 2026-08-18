# Tasks: Generic HTTP Adapter (Phase 9)

Tasks follow strict RED → GREEN → REFACTOR. Paths are exact. Work units with no dependency between them may proceed in parallel after the contract checkpoint; integration tasks wait for their declared predecessors. This artifact task creates no production code, commits, or pushes.

## Work Unit A — Config and wire contracts

- [x] A1 RED: add focused tests for `[adapters.generic_http]` loading, required fields, defaults, relative paths, HTTP(S) URL validation, finite timeout, bounded retries/backoff, and CLI base URL override; verify the tests fail for the missing adapter config contract.
- [x] A2 GREEN: add typed generic HTTP configuration and safe validation in the CLI/config seam, preserving existing `CliConfig` behavior and preventing network I/O on invalid settings.
- [x] A3 RED: add Pydantic wire-model tests for retrieve `{chunks: [...]}` and answer `{answer: str}`, including strict UUID/numeric/type validation and extra-field policy.
- [x] A4 GREEN: implement strict request/response models and typed adapter error classes under `src/ragfence/adapters/`; map only validated payloads to `RetrievedChunk`/`str`.
- [x] A5 REFACTOR: run A tests plus existing config/model tests; consolidate defaults and error messages, keeping secrets out of all validation errors.

## Work Unit B — HTTP transport and authentication (parallel with C after A)

- [x] B1 RED: add FastAPI-stub tests for safe URL joining, JSON POST/GET methods, finite timeout propagation, status handling, and static `Bearer` header injection.
- [x] B2 GREEN: implement the minimal transport helper with normalized base URL, operation-safe endpoint context, finite timeout, and configured static auth header.
- [x] B3 RED: add tests proving non-transient 4xx responses are not retried, transient health failures are retried, and exponential backoff is bounded via an injectable sleeper/clock.
- [x] B4 GREEN: implement health-only retry/backoff for connection errors, timeouts, and 5xx responses; do not replay retrieve/answer POSTs.
- [x] B5 REFACTOR: run transport tests with a real local FastAPI stub and inspect captured logs/exceptions to prove token and authorization values never appear.

## Work Unit C — Strict response mapping (parallel with B after A)

- [x] C1 RED: add FastAPI-stub tests for valid retrieve/answer mappings, non-JSON bodies, missing fields, null values, malformed UUIDs, invalid chunk items, and non-2xx responses.
- [x] C2 GREEN: implement strict Pydantic parsing and domain mapping; raise typed parse/transport errors instead of returning partial/empty success.
- [x] C3 RED: add tests for optional `answer_path`, empty-but-valid answer strings, metadata preservation, and target extra-field stripping.
- [x] C4 GREEN: implement explicit unsupported-answer behavior and normalized context serialization without changing canonical domain models.
- [x] C5 REFACTOR: run mapping tests and existing core/protocol tests; remove duplicate parsing and make operation/error naming stable.

## Work Unit D — GenericHTTPAdapter integration

- [x] D1 RED: add adapter-level tests asserting the `RAGAdapter` protocol surface, `name`, request payloads, retrieve/answer delegation, health result, and no accidental retries on POST operations; depends on B5 and C5.
- [x] D2 GREEN: create `src/ragfence/adapters/generic_http.py`, export it from the adapter package, and wire configuration into its constructor; depends on D1.
- [x] D3 RED: add timeout and health-exhaustion tests asserting typed failures/`False`, bounded attempt counts, and safe case-level error evidence; depends on D2.
- [x] D4 GREEN: complete failure translation and health semantics used by the Phase 8 evaluation engine; depends on D3.
- [x] D5 REFACTOR: run all adapter-focused tests, type checks, and lint; preserve the protocol boundary and document operation semantics; depends on D4.

## Work Unit E — CLI and evaluation integration

- [x] E1 RED: add Typer tests for `ragfence adapter check generic_http` success, invalid config, unhealthy target, safe output, and exit code 2; depends on D5.
- [x] E2 GREEN: replace the placeholder adapter-check seam with generic HTTP construction and `is_healthy()` invocation, honoring config plus `--base-url`; depends on E1.
- [x] E3 RED: add CLI/evaluation tests for `ragfence test --adapter generic_http --base-url <stub>`, report writing, threshold exit codes, and evidence containing bounded prompts/responses/verdicts without bearer tokens; depends on E2.
- [x] E4 GREEN: wire generic HTTP target selection into `evaluate()` while preserving Phase 8 report/evidence and existing reference adapter behavior; depends on E3.
- [x] E5 REFACTOR: run focused CLI/evaluation tests and all existing CLI/report tests; verify no regression in reference mode or legacy threshold conversion; depends on E4.

## Work Unit F — End-to-end FastAPI stub verification

- [x] F1 RED: add reusable local FastAPI stub fixtures/routes for `/retrieve`, `/chat`, `/health`, configurable response bodies/statuses/delays, and request capture; depends on A5 and D5.
- [x] F2 GREEN: use the stub to cover the complete happy path from adapter call through evaluation report artifact, including retrieval-only mode and optional answer mode; depends on F1 and E4.
- [x] F3 RED: add integration cases for non-JSON, missing fields, timeout, retry exhaustion, 4xx no-retry, auth redaction, and malformed health response; depends on F2.
- [x] F4 GREEN: fix only the minimal adapter/CLI/evidence behavior required by those failing scenarios; depends on F3.
- [x] F5 REFACTOR: run the full non-DB test suite, FastAPI-stub integration suite, Ruff, formatting, and mypy; record actual results before marking Phase 9 ready; depends on F4.

## Verification and handoff

- [x] V1: confirm the active change contains exactly `proposal.md`, `design.md`, `specs/generic-http/spec.md`, and `tasks.md` before implementation; no production files are part of this artifact deliverable.
- [x] V2: require observed RED, GREEN, and REFACTOR evidence for every work unit, with FastAPI-stub results and secret-redaction assertions.
- [x] V3: verify `ragfence adapter check generic_http` and `ragfence test --adapter generic_http --base-url <stub>` against the existing CLI exit/report contracts before archive.

**Task count:** 33 total (A1–A5: 5, B1–B5: 5, C1–C5: 5, D1–D5: 5, E1–E5: 5, F1–F5: 5, V1–V3: 3).
