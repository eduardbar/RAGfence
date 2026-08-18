# CI Integration Specification

### Requirement: Reusable workflow contract

The project MUST provide a reusable GitHub Actions workflow at `.github/workflows/ragfence-test.yml` with `workflow_call` inputs for adapter, target/base URL, threshold, target startup, fake-provider mode, and optional PR comments. The workflow MUST remain a thin wrapper over the CLI and MUST support Python 3.12.

#### Scenario: Workflow is locally discoverable

- GIVEN the repository checkout and the workflow YAML file
- WHEN an offline structure test parses the YAML
- THEN the workflow declares `workflow_call`
- AND it declares a Python 3.12 matrix
- AND every required input has a documented default or is explicitly required
- AND the test does not contact GitHub or start a runner

#### Scenario: Existing baseline CI remains separate

- GIVEN the current `.github/workflows/ci.yml` quality workflow
- WHEN the Phase 11 workflow is added
- THEN the baseline lint/type/test workflow remains semantically unchanged
- AND service evaluation is represented by the separate reusable workflow

### Requirement: Ordered environment setup and target readiness

The reusable workflow MUST execute checkout, Python setup, dependency installation, `ragfence init --up`, target startup, and bounded target health/readiness in that order. Initialization or readiness failure MUST stop evaluation and fail the job.

#### Scenario: Target is initialized and started before evaluation

- GIVEN a valid target and installable repository
- WHEN the workflow job runs
- THEN checkout and Python 3.12 setup complete before installation
- AND `ragfence init --up` completes before target startup/readiness
- AND readiness completes before `ragfence test`
- AND no evaluation command is run when initialization or readiness fails

#### Scenario: Target never becomes healthy

- GIVEN a target that remains unreachable after bounded retries
- WHEN readiness handling completes
- THEN the job fails with a safe adapter-health error
- AND no success result is reported
- AND no secret-bearing URL, header, or environment dump is printed

### Requirement: CLI adapter, threshold, report, and exit contract

The workflow MUST invoke `ragfence test` with the selected adapter, target base URL, canonical 0–100 threshold, JSON output, and a deterministic report destination. It MUST preserve CLI exit semantics: 0 for score at/above threshold, 1 for below threshold, and 2 for configuration/runtime failure.

#### Scenario: Passing threshold gates green

- GIVEN a completed report with score equal to or above threshold
- WHEN the CLI returns 0
- THEN the final workflow gate returns 0
- AND the summary identifies a passed threshold
- AND the JSON report is available for upload

#### Scenario: Below threshold blocks the PR

- GIVEN a completed report with score below threshold
- WHEN `ragfence test` returns 1
- THEN the report and summary steps still run
- AND the final workflow gate returns 1
- AND the check is red so branch protection can block the PR
- AND the workflow does not convert exit 1 into success

#### Scenario: Configuration or runtime error fails closed

- GIVEN invalid CLI configuration, an execution crash, or an invalid threshold
- WHEN `ragfence test` returns 2 or the documented runtime-error status
- THEN the final workflow gate is nonzero
- AND the summary labels the result as an execution/configuration error rather than a threshold pass
- AND no completed score is invented

### Requirement: JSON artifact retention

The workflow MUST upload `.ragfence/reports/ci.json` (or the explicit configured report path) as a named JSON artifact after evaluation, including when evaluation returns exit 1. Upload MUST use `if: always()` while still failing if a required report is absent.

#### Scenario: Completed failing report is retained

- GIVEN a below-threshold evaluation that writes valid JSON
- WHEN the CLI step returns 1
- THEN the artifact upload step runs
- AND the uploaded JSON contains score, threshold, outcome, threshold status, and redacted findings
- AND the later final gate remains failed

#### Scenario: No report is not a false pass

- GIVEN initialization or evaluation fails before writing a report
- WHEN the artifact step runs
- THEN the workflow records the missing artifact as an error or explicit absence
- AND the final gate remains nonzero
- AND no empty synthetic success report is uploaded

### Requirement: Safe summary and PR comment

The workflow MUST write a bounded human-readable summary to `$GITHUB_STEP_SUMMARY` for every attempted evaluation. An optional PR comment MUST be marker-idempotent, use least privilege, and run only for a trusted same-repository PR context. Report values MUST be treated as data, not shell/program source.

#### Scenario: Summary is safe on a failing PR

- GIVEN a report containing findings and a below-threshold score
- WHEN summary generation runs after the CLI step
- THEN the summary includes score, threshold, outcome, passed-threshold status, and artifact name
- AND it contains no bearer token, DSN, authorization header, or unrestricted retrieved chunk content
- AND it does not use `eval`, an environment dump, or unquoted report interpolation

#### Scenario: Fork PR cannot trigger a write comment

- GIVEN a pull request whose head repository differs from the base repository
- WHEN the workflow evaluates the comment condition
- THEN no PR write API/action is executed
- AND the check, artifact, and job summary remain available

#### Scenario: Same-repository comment is idempotent

- GIVEN a trusted same-repository pull request and comments enabled
- WHEN the workflow completes more than once
- THEN the marker comment is updated/replaced rather than appended indefinitely
- AND the body contains only bounded redacted report fields

### Requirement: Deterministic fake-provider default

CI MUST select deterministic fake embedding and LLM providers by default and MUST NOT require external model credentials for the default path. The determinism guard MUST compare stable report fields while excluding run-specific timestamps/IDs.

#### Scenario: Default run needs no provider secret

- GIVEN no model/API credentials in the environment
- WHEN the default workflow configuration runs
- THEN fake providers are explicitly selected
- AND evaluation can reach the CLI without a real provider call
- AND no step logs a missing secret or secret-shaped environment value

#### Scenario: Repeated equivalent inputs have equivalent scores

- GIVEN two local fixture evaluations with identical commit/configuration/seed and fake providers
- WHEN their canonical report fields are compared
- THEN scores, thresholds, case/finding ordering, and deterministic fingerprint are identical
- AND timestamps and artifact run IDs are excluded from the comparison
- AND the test performs no GitHub or external-service call

### Requirement: Offline workflow verification

The implementation MUST include TDD tests that validate workflow YAML structure, command ordering, exit propagation, artifact/summary conditions, fake-provider defaults, comment safety, and secret-safe commands locally. These tests MUST use parser/fixture doubles and MUST NOT call GitHub Actions, GitHub APIs, Docker registries, external target services, or real model providers.

#### Scenario: Structure test catches a missing gate

- GIVEN a workflow fixture with the final exit propagation step removed
- WHEN the offline structural test suite runs
- THEN the suite fails with a focused assertion identifying the missing gate
- AND it does not attempt to execute the workflow

#### Scenario: Security test catches secret logging

- GIVEN a workflow fixture containing an environment dump or command that prints a token/header
- WHEN the offline security assertions run
- THEN the suite fails and identifies the unsafe command
- AND no credential is loaded or transmitted during the test
