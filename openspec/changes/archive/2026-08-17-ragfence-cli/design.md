# Design: RAGFence CLI

## Technical Approach

Keep `src/ragfence/cli/` as a thin shell. Command functions parse arguments, load configuration, invoke injected protocol-level seams, render a result, and translate outcomes into exit codes. Evaluation, adapter, retrieval, and persistence logic remain outside the CLI.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| ADR-1 | CLI framework | Existing Typer dependency | Already declared and used by the package entry point; preserves the current console-script contract. |
| ADR-2 | Configuration format | TOML via `tomllib` with environment overrides | Standard-library parser, deterministic behavior, no new dependency. |
| ADR-3 | Output modes | Plain text by default; `--json` for machine-readable output | Non-TTY-safe and suitable for local use and CI artifacts. |
| ADR-4 | Exit codes | 0 pass, 1 below threshold, 2 configuration/runtime error | Matches IMPLEMENTATION_PLAN and lets CI distinguish a security finding from a broken setup. |
| ADR-5 | Dependency seams | Typed protocols and injectable callables | Phase 6 can be tested before Phase 7/8 internals are complete and avoids business logic in `cli/`. |
| ADR-6 | Initialization safety | Refuse to overwrite by default; explicit `--force` required | Prevents accidental loss of local configuration. |

## Command Contract

```text
ragfence init [--path PATH] [--force] [--with-demo]
ragfence test [--config PATH] [--adapter NAME] [--base-url URL]
              [--threshold FLOAT] [--json] [--output PATH]
ragfence demo [--config PATH] [--up]
ragfence adapter check [NAME] [--config PATH] [--base-url URL] [--json]
```

The exact option names are frozen in the spec and tests before implementation. Commands must not log tokens, authorization headers, or full retrieved chunk contents.

## Configuration

`ragfence.toml` contains only non-secret settings and may include environment references. Environment variables override file values using a documented `RAGFENCE_` prefix. Missing or malformed configuration raises a typed configuration error converted to exit code `2`.

## Reporting

The report model is JSON-serializable and contains score, threshold, outcome, counts, and redacted findings. Text output is a stable summary with no ANSI codes when stdout is not a TTY. The report writer creates `.ragfence/reports/` and writes a deterministic filename or an explicit `--output` path.

## Testing Strategy

- Unit tests for TOML parsing, environment precedence, redaction, exit-code mapping, report formatting, and overwrite protection.
- Typer command tests for help, init, test pass/fail/error, demo, and adapter check.
- No network calls, Docker, API keys, or real database required for Phase 6 tests.
- Integration seams use deterministic fake evaluation and adapter results; Phase 7/8/9 replace those implementations without changing command contracts.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/ragfence/cli/main.py` | Modify | Register Phase 6 command tree and translate errors to exit codes. |
| `src/ragfence/cli/config.py` | Create | TOML loading, environment overrides, validation. |
| `src/ragfence/cli/reporting.py` | Create | Report model, redaction, text/JSON rendering, writer. |
| `src/ragfence/cli/errors.py` | Create | Typed configuration and runtime errors. |
| `tests/test_cli.py` | Modify | Preserve bootstrap help tests and add command contract tests. |
| `tests/test_cli_config.py` | Create | Configuration tests. |
| `tests/test_cli_reporting.py` | Create | Rendering and redaction tests. |

## Rollback Plan

Revert the Phase 6 files and restore the help-only command implementation. No database migration or deployed state is changed.
