# Tasks: Optional LLM Providers (Phase 10)

Tasks follow strict RED → GREEN → REFACTOR. Work units with no dependency may proceed in parallel after the contract checkpoint. This artifact-only change creates no production code, commits, or pushes.

## Work Unit A — Provider contracts, config, and selection

- [x] A1 RED: add tests for `fake`/`openai`/`anthropic`/`ollama` selection, default fake fallback, explicit missing-key errors, and no network on invalid config.
- [x] A2 GREEN: implement typed `[llm]` configuration and provider factory/selection metadata without changing `LLMProvider` or `LLMResponse`.
- [x] A3 RED: add tests for `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` precedence and prove keys are absent from metadata, errors, logs, and evidence.
- [x] A4 GREEN: wire BYOK reads and secret-safe configuration/error handling; add Ollama base URL/default validation.
- [x] A5 REFACTOR: run focused config/selection tests plus existing core/provider tests; keep all environment-dependent behavior injectable.

## Work Unit B — Standard-library HTTP transport (parallel with C/D after A1)

- [x] B1 RED: add local-stub tests for JSON POST requests, finite timeout propagation, status parsing, and provider-specific headers.
- [x] B2 GREEN: implement the minimal `urllib.request` transport with safe operation context and response-size bounds; do not add a mandatory SDK/dependency.
- [x] B3 RED: add tests for 429 retry, bounded exponential backoff, safe `Retry-After`, exhausted retries, 4xx no-retry, and timeout/5xx handling.
- [x] B4 GREEN: implement typed transport errors and bounded retry/backoff with injectable sleeper/clock.
- [x] B5 REFACTOR: inspect captured logs/exceptions/evidence to verify no API key or authorization header is disclosed.

## Work Unit C — OpenAI and Anthropic mappings (parallel with B/D after A1)

- [x] C1 RED: add stub tests for OpenAI chat payload/headers, `choices[0].message.content`, usage counts, and malformed responses.
- [x] C2 GREEN: implement `OpenAIProvider` over the shared stdlib transport, including configured model/base URL and safe errors.
- [x] C3 RED: add stub tests for Anthropic headers, system-message mapping, text-block extraction, usage counts, and malformed responses.
- [x] C4 GREEN: implement `AnthropicProvider` over the shared transport without importing an Anthropic SDK.
- [x] C5 REFACTOR: consolidate common mapping/error behavior and run provider-focused tests plus protocol conformance checks.

## Work Unit D — Ollama and fake/token semantics (parallel with B/C after A1)

- [x] D1 RED: add tests for Ollama configured/default base URL, non-streaming payload, response mapping, and no-key operation.
- [x] D2 GREEN: implement `OllamaProvider` over the shared stdlib transport; reject malformed content rather than fabricating answers.
- [x] D3 RED: add tests for a shared deterministic token estimator, authoritative usage precedence, and repeated fake completion equality.
- [x] D4 GREEN: implement/document deterministic token fallback and adjust `FakeLLMProvider` only as required to satisfy the protocol and count contract.
- [x] D5 REFACTOR: run all fake/Ollama/token tests and verify imports have no network side effects or optional SDK assumptions.

## Work Unit E — Evaluation generation gating (after A–D)

- [x] E1 RED: add evaluation tests proving fake output yields `WARNING`/`skipped: no_real_provider`, while retrieval/security metrics continue.
- [x] E2 GREEN: integrate provider real/fake metadata and gate faithfulness/answer-correctness metrics accordingly.
- [x] E3 RED: add tests proving successful real-provider completion enables generation metrics and provider latency/token operational metrics.
- [x] E4 GREEN: wire real-provider generation into the Phase 8 evaluation path and bounded evidence.
- [x] E5 RED→GREEN: add tests for real-provider timeout, malformed response, auth failure, and exhausted rate-limit retries marking the case failed without fake substitution; implement minimal failure translation, then refactor.

## Work Unit F — Offline end-to-end verification (after E)

- [x] F1 RED: create reusable local HTTP stubs for OpenAI, Anthropic, and Ollama routes with request capture and configurable status/body/delay.
- [x] F2 GREEN: exercise each provider through selection → completion → `LLMResponse` → evaluation metrics using only local stubs.
- [x] F3 RED: cover key redaction, 429 recovery/exhaustion, missing usage estimation, malformed JSON/schema, timeout, and explicit-provider failure paths.
- [x] F4 GREEN: fix only the minimal provider/evaluation behavior required by the failing integration tests.
- [x] F5 REFACTOR: run the full non-DB suite, focused provider/evaluation tests, Ruff, formatting, and mypy; record observed results before handoff.

## Verification and handoff

- [x] V1: confirm the active change contains exactly `proposal.md`, `design.md`, `specs/llm-providers/spec.md`, and `tasks.md`; no production files are included.
- [x] V2: require observed RED, GREEN, and REFACTOR evidence for each implementation unit; no real provider or credential is used in tests.
- [x] V3: verify default no-key execution is deterministic, real-provider generation is gated correctly, and secret-redaction assertions pass.

**Task count:** 33 total (A1–A5: 5, B1–B5: 5, C1–C5: 5, D1–D5: 5, E1–E5: 5, F1–F5: 5, V1–V3: 3).
