# Design: Optional LLM Providers

## Technical approach

Implement `src/ragfence/providers/llm.py` behind the existing `LLMProvider` protocol. The evaluation layer sees only `LLMResponse` and typed provider errors; it never imports vendor-specific code. Because `pyproject.toml` currently contains no HTTP client or provider SDK, use a small synchronous standard-library transport built on `urllib.request` and `urllib.error`, with finite timeout and injectable sleeper for tests. Optional third-party SDKs are not assumed or required.

The existing `FakeLLMProvider` remains the deterministic fallback and should be adjusted only if needed to make token-count semantics explicit. Provider selection belongs at the configuration/factory boundary, not inside evaluation logic.

## Provider wire contracts

- **OpenAI:** `POST {base_url}/v1/chat/completions`, JSON `{model, messages: [{role, content}], temperature}`; bearer key from `OPENAI_API_KEY`; read `choices[0].message.content` and `usage.prompt_tokens`/`usage.completion_tokens` when present.
- **Anthropic:** `POST {base_url}/v1/messages`, JSON `{model, system?, messages, max_tokens, temperature}`; headers `x-api-key` and `anthropic-version` from fixed configuration; read text blocks from `content` and `usage.input_tokens`/`usage.output_tokens` when present. System messages are separated according to the API contract.
- **Ollama:** `POST {base_url}/api/chat`, JSON `{model, messages, stream: false, options: {temperature}}`; no key; read `message.content` and `prompt_eval_count`/`eval_count` when present. Default base URL is local and configurable.

These are HTTP JSON contracts, not SDK contracts. Exact model names, API versions, and paths are configuration values with documented defaults; malformed or unexpected payloads fail closed.

## Configuration and selection

A typed `[llm]` config contains `provider` (`fake`, `openai`, `anthropic`, `ollama`), model, temperature, timeout, max retries, backoff, and optional provider base URLs. Environment variables override only secrets/configured secret values: `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`. Selection rules:

1. Explicit `fake` always selects fake.
2. Explicit `openai`/`anthropic` requires its key before network I/O; missing key is a safe configuration error, not a silent real-provider request.
3. Explicit `ollama` uses its base URL and does not require a key.
4. An automatic/default mode selects a configured usable real provider, otherwise fake. The selected provider and whether it is `real` are exposed as non-secret metadata.
5. Provider responses and diagnostics are bounded; request headers and secrets are redacted before logging/evidence.

## Token counting and metrics

`LLMResponse.prompt_tokens` and `completion_tokens` are required integers. Prefer authoritative usage fields returned by the provider. If a response omits usage, use one shared deterministic estimator (documented as an estimate, based on normalized UTF-8 text/whitespace rather than a vendor tokenizer) so tests do not depend on SDKs. Fake output remains deterministic and reports deterministic counts. Cost/latency may consume these counts, but generation quality metrics must be marked unavailable for fake mode.

The evaluation integration tags a provider as `real` only for OpenAI, Anthropic, or Ollama. `faithfulness` and `answer correctness` are enabled only for `real`; fake generation produces a deterministic answer for plumbing but causes generation scenarios to be `WARNING` with an explicit `skipped: no_real_provider` reason. Retrieval/security metrics continue normally.

## Failure and retry policy

All external calls have a finite timeout. Retry only rate-limit responses (HTTP 429, honoring a safe bounded `Retry-After` if present) and transient transport/5xx failures if the provider contract permits; never retry malformed requests, authentication/authorization 4xx, or non-idempotent calls beyond the explicit bounded policy. Use exponential backoff with a maximum delay and injectable sleeper. Exhaustion raises a typed error safe for logs. The evaluation engine records a bounded provider failure and marks the affected real-provider case failed; it must not substitute fake output after a real provider was explicitly selected.

## Parallel work units

| Unit | Owns | Depends on | Parallel |
|---|---|---|---|
| A. Contract/config | typed config, selection rules, provider metadata/errors | existing protocol/models | with B |
| B. HTTP transport | stdlib request helper, timeout, redaction, retry/backoff | existing protocol | with C after contract checkpoint |
| C. Provider mappings | OpenAI/Anthropic/Ollama payloads and strict response parsing | A + B interfaces | providers can proceed in parallel |
| D. Fake/token semantics | deterministic fake tests, shared token estimator, conformance | existing fakes/models | with B/C |
| E. Evaluation integration | real-provider gating, warning/skipped, failure evidence | A–D | after provider contract |
| F. End-to-end verification | local stubs, secret redaction, selection matrix | A–E | final |

Every implementation unit follows RED → GREEN → REFACTOR. This artifact creates no production code.

## Security and operational decisions

- Keys are read from environment/config only, never printed, logged, interpolated into exception text, or stored in evidence.
- Prompts/responses are bounded and redacted using existing observability rules; only `LLMResponse.content` may enter evidence, truncated.
- No implicit network call occurs merely by importing providers or loading invalid configuration.
- Fake mode requires no external dependency and is the deterministic CI/default path.
