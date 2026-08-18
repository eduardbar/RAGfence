# Release Readiness Specification

### Requirement: Documentation and contributor contract

The release MUST provide internally consistent product/technical/application/schema/plan documentation, a runnable README quickstart, contribution guidance, an inclusive Code of Conduct with a reporting route, and a changelog. Canonical names, supported Python/package versions, commands, report paths, adapter names, prerequisites, and exit semantics MUST agree across the public surfaces.

#### Scenario: Full documentation pass is consistent

- GIVEN the six documents under `docs/`, `README.md`, and `CONTRIBUTING.md`
- WHEN an offline consistency checker resolves referenced paths, commands, canonical model/adapter names, and exit codes
- THEN every referenced artifact exists or is explicitly marked future/out of scope
- AND no document contradicts `TRD.md` or Phase 12
- AND README links reach contribution, conduct, changelog, and the docs index

#### Scenario: New contributor follows the README

- GIVEN a clean Python >= 3.12 environment with no API keys
- WHEN the contributor follows the README quickstart
- THEN installation, `ragfence --help`, initialization, test execution, report location, and exit-code meanings are clear and executable
- AND the instructions distinguish offline checks from optional Docker database checks

### Requirement: Wheel build and isolated install

The project MUST build a wheel with the declared build tool and install that wheel into a fresh non-editable environment. The installed distribution MUST import and expose the `ragfence` console script without accidentally reading the checkout.

#### Scenario: Wheel smoke succeeds outside the checkout

- GIVEN a clean checkout and disposable build/venv directories outside the source tree
- WHEN `uv build` is followed by wheel-only installation
- THEN metadata, import, `ragfence --help`, and the documented smoke command succeed
- AND the wheel contains required runtime package files but no secrets or unintended repository files

### Requirement: Examples and local generic HTTP stub

The release MUST provide valid, non-secret reference and `[adapters.generic_http]` example configurations plus a minimal deterministic local HTTP stub matching the strict adapter wire contract.

#### Scenario: Example configurations validate offline

- GIVEN each checked-in example configuration
- WHEN it is parsed and validated without network access
- THEN required reference/generic HTTP keys, relative endpoint paths, bounded timeouts/retries, and localhost/placeholders are accepted
- AND no actual token, DSN, API key, or secret-shaped value is present

#### Scenario: Generic HTTP example runs against the stub

- GIVEN the local stub and the generic HTTP example
- WHEN `ragfence adapter check generic_http` and `ragfence test --adapter generic_http --base-url <stub>` run
- THEN health, strict response mapping, report generation, and documented 0/1/2 exit semantics work
- AND malformed, timeout, and non-JSON cases fail closed without logging credentials or full sensitive payloads

### Requirement: Clean end-to-end reference path

The release MUST verify `init → seed → test → report` on a clean environment with deterministic synthetic Acme data, no external keys, and a disposable PostgreSQL 16 + pgvector service where database-backed behavior is required.

#### Scenario: Offline E2E prerequisites remain runnable

- GIVEN no Docker daemon and no provider credentials
- WHEN the offline E2E/preflight suite runs
- THEN CLI/config/report and fake-provider checks pass using local doubles
- AND DB-gated checks are explicitly marked skipped with their prerequisite, never falsely reported as passed

#### Scenario: Docker-backed reference E2E produces evidence

- GIVEN a disposable healthy PostgreSQL + pgvector container
- WHEN initialization/migrations, deterministic seed, reference evaluation, and report writing run in order
- THEN reseeding is idempotent, expected Acme trap/authorization outcomes are present, tenant isolation holds, and the report is non-empty and schema-valid
- AND no external API key or network provider is required
- AND a below-threshold result returns 1 while a configuration/runtime failure returns 2

### Requirement: Acme performance sanity

The release MUST measure deterministic Acme embedding and authorized search separately for setup and steady state, record environment/corpus/query/latency/error data, and compare it with the v0.1 budget frozen from canonical documentation.

#### Scenario: Performance is within the release budget

- GIVEN the canonical budget is available or has been explicitly frozen before implementation GREEN
- WHEN the Acme benchmark runs against the reference seams
- THEN embedding and search measurements are within budget with the required p50/p95 evidence
- AND repeated runs are comparable and require no external provider
- AND leakage/unauthorized retrieval remains zero

### Requirement: Public CI and offline workflow verification

The release MUST preserve green baseline CI and the reusable RAGFence evaluation workflow contract. Offline tests MUST inspect both YAML files and must not contact GitHub, registries, or external targets. Public-main green status MUST be evidenced by a live run receipt.

#### Scenario: CI contracts are verified offline

- GIVEN `.github/workflows/ci.yml` and `.github/workflows/ragfence-test.yml`
- WHEN the offline workflow checker parses them
- THEN baseline install/lint/format/type/test and evaluation init/readiness/report/artifact/final-gate steps remain present and ordered
- AND fake providers, bounded readiness, secret-safe summary, and exit propagation are asserted
- AND no runner or network is started

#### Scenario: Public main is green

- GIVEN the release candidate commit on the public repository
- WHEN the maintainer checks the required `main` CI runs
- THEN the required checks are green for that commit
- AND the release record contains the run URL/identifier and commit SHA
- AND local/offline results are not substituted for this receipt

### Requirement: Dependency, history, and secret audit

The release MUST audit declared/locked dependencies and repository contents/history for known vulnerabilities and secrets. Findings MUST be clean or explicitly release-blocking with owner and waiver rationale; examples, reports, and logs MUST be secret-safe.

#### Scenario: Dependency audit is reproducible

- GIVEN the lockfile and clean wheel environment
- WHEN `uv audit` or the documented `pip-audit` fallback runs
- THEN the command completes with no unwaived release-blocking vulnerability
- AND the exact tool/version/input and findings are recorded

#### Scenario: No secrets are released

- GIVEN tracked files, generated release artifacts, examples, and reachable repository history
- WHEN offline secret scanners and targeted policy checks run
- THEN no credential, bearer token, DSN password, provider key, or environment dump is found
- AND `.env.example` contains placeholders only
- AND redaction checks prove reports/logs omit secrets and unrestricted retrieved content
