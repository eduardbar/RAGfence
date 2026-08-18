# Proposal: RAGFence CLI (Phase 6)

## Intent

Deliver the user-facing CLI orchestration layer for RAGFence (IMPLEMENTATION_PLAN Phase 6). The existing `ragfence` entry point is only a help stub; this change adds deterministic commands for initializing a local project, running evaluation suites, starting the reference demo, and validating adapters.

## Scope

### In Scope

- Typer commands: `ragfence init`, `ragfence test`, `ragfence demo`, and `ragfence adapter check`.
- `ragfence.toml` configuration loading with environment-variable overrides.
- Plain-text and JSON report output under `.ragfence/reports/`.
- Stable exit codes: success `0`, threshold failure `1`, configuration/runtime error `2`.
- Non-TTY output without ANSI escape sequences.
- Thin CLI orchestration over existing and future `evaluation`, `adapters`, dataset, and reference-service seams.
- Unit and command-level tests using Typer's runner; no external API keys required.

### Out of Scope

- Attack scenario definitions and evaluation engine internals (Phase 7/8).
- Generic HTTP adapter implementation (Phase 9); this change only validates the adapter contract and provides a seam.
- Real LLM providers (Phase 10).
- Web UI, authentication endpoints, or production deployment orchestration.

## Capabilities

### New Capabilities

- `cli`: deterministic command surface, configuration, report rendering, and exit-code behavior.

### Modified Capabilities

- `bootstrap`: replace the help-only CLI behavior with the Phase 6 command surface while preserving `ragfence --help` compatibility.

## Dependencies

- Completed Phases 0–5: package entry point, domain models, dataset, authorization, and secure retrieval.
- Future Phase 7/8 interfaces may be represented by narrow protocols or deterministic fakes; CLI must not embed evaluation business logic.

## Success Criteria

- `ragfence --help` and every Phase 6 command have stable help output and exit behavior.
- `ragfence init` creates a minimal config and report directory without overwriting an existing config unless explicitly requested.
- `ragfence test` runs through an injectable evaluation seam, renders text or JSON, and returns the documented exit code.
- `ragfence demo` and `ragfence adapter check` fail clearly with exit code `2` when required configuration or dependencies are unavailable.
- Secrets are read only from environment/config references and never printed in reports.
- Full quality gates remain green without Docker or API keys.
