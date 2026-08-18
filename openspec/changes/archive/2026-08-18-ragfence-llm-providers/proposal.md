# Proposal: Optional LLM Providers (Phase 10)

## Intent

Add an optional, protocol-bound generation seam for RAGFence. The evaluation engine will be able to use OpenAI, Anthropic, or local Ollama over HTTP while retaining a deterministic `FakeLLMProvider` as the zero-key default. Generation remains opt-in: retrieval/security evaluation must work without network access or credentials, and generation metrics are only authoritative when a real provider is configured.

## Scope

### In scope

- `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`, and the existing deterministic `FakeLLMProvider`, all conforming to `src/ragfence/core/protocols.py`.
- A provider factory/selection seam driven by `[llm]` configuration and explicit environment overrides.
- BYOK from `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`; keys are read at request/provider construction time and are never logged, returned in errors, persisted in evidence, or rendered in reports.
- Ollama configurable base URL, with a safe local default and no API key requirement.
- Provider HTTP request/response mapping to `Message` and `LLMResponse`, including provider usage fields and deterministic fallback token estimation when usage is absent.
- Bounded rate-limit retry/backoff, finite timeouts, typed failures, and evaluation-level case failure for exhausted real-provider errors.
- Deterministic fake fallback when no usable real provider is configured.
- Generation metric gating: `faithfulness` and `answer correctness` run only with a real provider; otherwise generation cases are marked `WARNING`/skipped rather than treated as measured passes.
- TDD tests using local HTTP stubs; no live provider, SDK, key, or network is required.

### Out of scope

- Mandatory provider dependencies, vendor SDK imports, embedding providers, streaming/tool calls, model fine-tuning, prompt-template frameworks, or a plugin registry.
- Changes to authorization, retrieval policy, canonical `LLMProvider`/`LLMResponse` protocol shape, persistence schema, or production implementation in this artifact-only change.
- Logging prompts, full documents, API keys, authorization headers, or unbounded provider responses.

## Dependencies and compatibility

This change depends on Phase 8 evaluation/reporting and preserves the existing `LLMProvider.complete(messages, temperature)` boundary. `FakeLLMProvider` remains importable from `src/ragfence/providers/fakes.py`. Existing `pyproject.toml` has no HTTP client or vendor SDK dependency; implementation should use Python standard-library HTTP (`urllib.request`/`urllib.error`) unless a separately approved optional extra is introduced. No SDK may be assumed.

## Success criteria

- Provider selection is explicit, validates configuration before network I/O, and defaults deterministically to fake mode when no real credentials/configuration are available.
- OpenAI, Anthropic, and Ollama HTTP responses map to `LLMResponse`; provider usage is preserved when supplied and token counts are always non-negative and deterministic.
- 429/rate-limit responses retry only within a bounded exponential-backoff budget; timeouts, malformed responses, auth errors, and exhausted retries fail the real-provider case with safe evidence.
- A local stub test proves keys reach only the intended request header and never appear in logs/errors/evidence.
- With a real provider, generation metrics execute end-to-end; without one, the suite completes deterministically with fake output and reports generation as `WARNING`/skipped.
