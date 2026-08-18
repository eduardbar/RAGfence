# Spec: Optional LLM Providers

## Requirements

### Requirement: Providers implement the canonical LLM contract

The system MUST provide `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`, and deterministic `FakeLLMProvider` implementations conforming to `LLMProvider.complete(messages, temperature)` and returning `LLMResponse`.

#### Scenario: Fake completion is deterministic

- GIVEN the same ordered `Message` list and temperature
- WHEN `FakeLLMProvider.complete` is called repeatedly
- THEN the content and token counts are identical
- AND no network, SDK, or environment secret is read

#### Scenario: Provider response maps to the domain model

- GIVEN a valid provider JSON response containing completion content
- WHEN the corresponding provider completes a request
- THEN it returns one `LLMResponse` with string content and non-negative integer token counts
- AND no vendor response object escapes the provider boundary

### Requirement: Provider selection is explicit and safe

The system MUST select providers from typed `[llm]` configuration with `fake`, `openai`, `anthropic`, and `ollama` options. Missing usable credentials in automatic/default mode MUST select fake; an explicitly requested keyed provider without its key MUST fail configuration before network I/O.

#### Scenario: No key uses deterministic fallback

- GIVEN no usable `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` and no explicit Ollama configuration
- WHEN the default provider is selected
- THEN `FakeLLMProvider` is selected
- AND the selection is marked non-real
- AND no external request is made

#### Scenario: Explicit provider is honored

- GIVEN `provider=ollama` and a valid base URL
- WHEN selection runs
- THEN `OllamaProvider` is returned even when cloud keys are absent
- AND provider metadata does not expose any secret

#### Scenario: Missing explicit key fails closed

- GIVEN `provider=openai` or `provider=anthropic` and its required environment variable is absent
- WHEN selection runs
- THEN a safe configuration error is raised before HTTP transport starts
- AND fake output is not silently substituted

### Requirement: BYOK secrets are never disclosed

The system MUST read `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` as BYOK credentials and MUST exclude their values and derived authorization headers from logs, exceptions, evidence, reports, and normal provider metadata.

#### Scenario: Key is sent only to the intended provider

- GIVEN `OPENAI_API_KEY` is set and OpenAI is selected
- WHEN a completion request is sent to the local HTTP stub
- THEN the stub receives the expected bearer header
- AND an Anthropic or Ollama request is not made

#### Scenario: Provider failure is secret-safe

- GIVEN a configured provider returns an error
- WHEN the error is logged or recorded as bounded evidence
- THEN neither the API key nor the full authorization header appears
- AND only provider name, operation, status class, and safe error context remain

### Requirement: Ollama uses a configurable local base URL

`OllamaProvider` MUST use a configured base URL, defaulting to the documented local Ollama endpoint, and MUST send non-streaming chat requests without requiring a cloud key.

#### Scenario: Ollama completion uses configured URL

- GIVEN base URL `http://127.0.0.1:11434` and model `llama3`
- WHEN completion runs
- THEN it POSTs to the Ollama chat endpoint with `stream=false`
- AND it maps `message.content` to `LLMResponse.content`

### Requirement: Token counting is stable and bounded

Providers MUST return non-negative prompt and completion token counts. Authoritative provider usage fields MUST be preferred; when usage is absent, a shared documented deterministic estimator MUST be used. The implementation MUST NOT require a vendor tokenizer SDK.

#### Scenario: Usage fields are preserved

- GIVEN a valid response with provider usage counts
- WHEN it is mapped
- THEN those counts populate `LLMResponse`
- AND counts are not inferred from response content when authoritative values exist

#### Scenario: Missing usage is estimated deterministically

- GIVEN identical normalized messages and completion content with no usage object
- WHEN mapping runs twice
- THEN both responses contain identical non-negative estimated counts
- AND the result is labeled/treated as an estimate where metrics expose that distinction

### Requirement: Rate limits retry with bounded backoff

The HTTP layer MUST retry rate-limit responses (429) using bounded exponential backoff, honoring only a safe bounded `Retry-After` value when present. It MUST stop after configured attempts and MUST not loop indefinitely.

#### Scenario: Rate limit resolves within budget

- GIVEN a provider stub returns 429 twice and then a valid response
- WHEN completion runs with at least three attempts configured
- THEN it waits between attempts using bounded backoff
- AND returns the valid `LLMResponse`

#### Scenario: Rate limit budget is exhausted

- GIVEN every provider attempt returns 429
- WHEN the retry budget is exhausted
- THEN a typed provider-rate-limit error is raised
- AND the request does not continue retrying
- AND the evaluation case is marked failed with safe bounded evidence

### Requirement: Provider failures fail real-provider cases

Timeouts, transport errors, non-2xx non-rate-limit responses, malformed JSON, and schema-invalid content MUST raise typed safe errors. When a real provider was explicitly selected, the evaluator MUST mark the affected case failed and MUST NOT replace the failure with fake output.

#### Scenario: Malformed completion fails closed

- GIVEN a provider returns JSON without required completion content
- WHEN completion maps the response
- THEN it raises a typed validation/provider error
- AND it returns no partial or fabricated answer

#### Scenario: Timeout fails the case

- GIVEN the provider exceeds its finite timeout
- WHEN completion runs
- THEN it raises a typed timeout error after the bounded attempt policy
- AND evidence omits request secrets and unbounded response content

### Requirement: Generation metrics require a real provider

`faithfulness` and `answer correctness` MUST execute only when a real provider (`openai`, `anthropic`, or `ollama`) is configured and successfully completes. Fake fallback MUST keep the suite deterministic while marking generation as `WARNING`/skipped with an explicit reason.

#### Scenario: No real provider skips generation metrics

- GIVEN provider selection resolves to `FakeLLMProvider`
- WHEN a generation scenario is evaluated
- THEN deterministic fake generation may run for pipeline plumbing
- AND faithfulness and answer correctness are not reported as measured values
- AND the scenario is `WARNING` with `skipped: no_real_provider`
- AND retrieval/security scenarios continue to be evaluated normally

#### Scenario: Real provider enables generation metrics

- GIVEN a configured real provider returns a valid completion
- WHEN a generation scenario is evaluated
- THEN faithfulness and answer correctness are eligible to run
- AND provider latency and token counts are available to operational metrics

### Requirement: Tests are offline and deterministic

The implementation MUST include TDD coverage using local HTTP stubs for each provider's happy path, selection, token counts, 429 retry/exhaustion, malformed responses, timeout/failure handling, secret redaction, and fake fallback. Tests MUST not require real keys, SDKs, network, or a running Ollama service.

#### Scenario: Offline provider suite covers failure classes

- GIVEN local stubs configured with valid, 429, timeout, malformed, and auth-error responses
- WHEN the provider test suite runs
- THEN all documented success/failure behaviors are asserted deterministically
- AND no test emits a real credential or depends on an external service
