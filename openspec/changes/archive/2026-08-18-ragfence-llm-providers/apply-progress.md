# Apply Progress: Optional LLM Providers (Phase 10)

## Work Units A–D — Contracts, transport, providers, tokens

- RED → GREEN → REFACTOR completed with offline local request doubles.
- Typed `[llm]` selection supports fake/openai/anthropic/ollama/auto with secret-safe BYOK and deterministic fake fallback.
- Standard-library transport provides bounded JSON responses, timeout, 429/5xx retry/backoff, 4xx no-retry, and safe diagnostics.
- OpenAI, Anthropic, and Ollama payload/response mappings are strict; usage fields take precedence and missing usage uses deterministic estimation.
- Fake provider remains deterministic and has no network side effects.

## Work Units E–F — Evaluation gating and offline E2E

- Fake generation is explicitly `WARNING`/`skipped: no_real_provider`; retrieval/security metrics continue.
- Real provider metadata enables generation/operational metrics; explicit real-provider failures do not silently fall back to fake.
- Offline stubs cover provider selection, OpenAI/Anthropic/Ollama completion, malformed responses, timeouts, 429 recovery/exhaustion, usage estimation, and key redaction.

## Verification evidence

- `RAGFENCE_TEST_DATABASE_DSN=...localhost:5434/ragfence uv run pytest -q`: 384 passed, 0 skipped.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `uv run mypy`: passed, 63 source files.
- `uv build`: passed; wheel and source distribution created.
- No real keys, external network, commit, push, or deploy used.
