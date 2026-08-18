# Spec for cli

## Requirements

### Requirement: Command Surface

The system MUST expose `ragfence init`, `ragfence test`, `ragfence demo`, and `ragfence adapter check` through the installed console script. Existing `ragfence --help` behavior MUST remain valid.

#### Scenario: Help lists Phase 6 commands

- GIVEN the package is installed
- WHEN `ragfence --help` is invoked
- THEN it exits with code 0
- AND the help text lists `init`, `test`, `demo`, and `adapter`

#### Scenario: Adapter check help is available

- GIVEN the package is installed
- WHEN `ragfence adapter check --help` is invoked
- THEN it exits with code 0
- AND it documents the adapter name and base URL options

### Requirement: Initialization

`ragfence init` MUST create a minimal `ragfence.toml` and `.ragfence/reports/` under the selected path. It MUST NOT overwrite an existing config unless `--force` is supplied.

#### Scenario: Init creates project files

- GIVEN an empty temporary directory
- WHEN `ragfence init --path <dir>` is invoked
- THEN it exits with code 0
- AND `ragfence.toml` exists
- AND `.ragfence/reports/` exists

#### Scenario: Init protects existing configuration

- GIVEN a directory containing `ragfence.toml`
- WHEN `ragfence init --path <dir>` is invoked without `--force`
- THEN it exits with code 2
- AND the existing file content is unchanged

### Requirement: Configuration Precedence

The CLI MUST load TOML configuration and MUST allow documented `RAGFENCE_` environment variables to override file values. Invalid TOML or invalid values MUST produce a configuration error without a traceback in normal CLI output.

#### Scenario: Environment overrides file

- GIVEN a config file with threshold `0.8`
- AND `RAGFENCE_THRESHOLD=0.9`
- WHEN a command loads configuration
- THEN the effective threshold is `0.9`

#### Scenario: Invalid configuration returns a controlled error

- GIVEN malformed TOML or an invalid threshold
- WHEN a command loads configuration
- THEN it exits with code 2
- AND the output identifies configuration failure without exposing a traceback by default

### Requirement: Evaluation Command

`ragfence test` MUST invoke an injectable evaluation seam, render a report, and return exit code 0 when the score meets the threshold, 1 when it is below the threshold, and 2 for configuration/runtime errors.

#### Scenario: Passing evaluation

- GIVEN a deterministic evaluation result with score equal to or above the threshold
- WHEN `ragfence test` is invoked
- THEN it exits with code 0
- AND it writes a report

#### Scenario: Failing threshold

- GIVEN a deterministic evaluation result below the threshold
- WHEN `ragfence test` is invoked
- THEN it exits with code 1
- AND the report contains the score and threshold

#### Scenario: JSON report mode

- GIVEN a completed evaluation
- WHEN `ragfence test --json` is invoked
- THEN stdout or the selected output contains valid JSON
- AND the JSON contains score, threshold, outcome, and redacted findings

### Requirement: Safe Reporting

Reports MUST omit secrets and MUST NOT include full retrieved chunk contents by default. Text output MUST contain no ANSI escape sequences when stdout is not a TTY. Report files MUST be written below `.ragfence/reports/` unless an explicit output path is supplied.

#### Scenario: Secret redaction

- GIVEN an evaluation finding containing a bearer token or authorization header
- WHEN a report is rendered
- THEN the secret value is absent from text and JSON output

#### Scenario: Plain non-TTY output

- GIVEN stdout is not a TTY
- WHEN a report is rendered in text mode
- THEN the output contains no ANSI escape sequences

### Requirement: Adapter and Demo Commands

`ragfence adapter check` and `ragfence demo` MUST use injectable seams and MUST return a controlled configuration/runtime error with exit code 2 when their required configuration or service is unavailable. They MUST not silently claim success.

#### Scenario: Adapter check reports unavailable target

- GIVEN a configured target that is unreachable
- WHEN `ragfence adapter check` is invoked
- THEN it exits with code 2
- AND the output identifies the target as unavailable

#### Scenario: Demo reports missing local service

- GIVEN the reference service is not available and `--up` is not requested
- WHEN `ragfence demo` is invoked
- THEN it exits with code 2
- AND the output explains how to start or configure the service
