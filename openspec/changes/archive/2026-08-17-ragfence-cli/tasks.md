# Tasks: RAGFence CLI (Phase 6)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~450 |
| 400-line budget risk | Medium |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | stacked-to-main |

## Phase 1: Contracts and Configuration

- [x] 1.1 RED: add command-surface tests for `ragfence --help` and subcommand help; verify current stub fails for Phase 6 commands.
- [x] 1.2 RED: add config tests for TOML parsing, defaults, environment precedence, malformed TOML, and invalid threshold.
- [x] 1.3 GREEN: create `src/ragfence/cli/errors.py` and `config.py` with typed errors, `tomllib` loading, validation, and `RAGFENCE_` overrides.
- [x] 1.4 GREEN: modify `src/ragfence/cli/main.py` to register the command group and preserve the existing `--help` contract.
- [x] 1.5 REFACTOR: run focused CLI/config tests, Ruff, and mypy; freeze command and configuration contracts.

## Phase 2: Reporting and Init

- [x] 2.1 RED: add report tests for pass/fail outcomes, stable text, JSON serialization, ANSI-free non-TTY output, and secret/chunk redaction.
- [x] 2.2 GREEN: create `src/ragfence/cli/reporting.py` with typed report data, redaction, renderers, and report writer.
- [x] 2.3 RED: add `init` tests for directory creation, default config, existing-config refusal, and `--force` replacement.
- [x] 2.4 GREEN: implement `ragfence init` with safe overwrite behavior and `.ragfence/reports/` creation.
- [x] 2.5 REFACTOR: run focused reporting/init tests and verify generated files are deterministic.

## Phase 3: Test, Demo, and Adapter Commands

- [x] 3.1 RED: add deterministic fake evaluation seam tests for threshold pass, threshold failure, JSON output, and runtime error mapping.
- [x] 3.2 GREEN: implement `ragfence test` orchestration over the injectable evaluation seam with exit codes 0/1/2.
- [x] 3.3 RED: add tests for unavailable demo service and adapter target, including controlled error output.
- [x] 3.4 GREEN: implement `ragfence demo` and `ragfence adapter check` over injectable seams; no silent success.
- [x] 3.5 REFACTOR: run all CLI tests and confirm no business logic leaks into `cli/`.

## Phase 4: Verification and Handoff

- [x] 4.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and `uv build`.
- [x] 4.2 Run `gentle-ai sdd-status ragfence-cli` and confirm all tasks are complete before final verification.
- [x] 4.3 Record apply-progress evidence for every RED → GREEN unit and prepare the verification report.
- [x] 4.4 Document Phase 7/8 integration seams and hand off frozen CLI/report contracts.
