# Proposal: RAGFence CI Integration (Phase 11)

## Intent

Deliver the Phase 11 CI contract as an OpenSpec change: a reusable GitHub Actions workflow that is a thin wrapper around the already-defined RAGFence CLI, adapter, evaluation, and report contracts. A consumer should be able to invoke the workflow for a target service and receive a deterministic JSON security report, a human-readable PR summary, and a blocking check when the weighted score is below the configured threshold.

The existing `.github/workflows/ci.yml` is the baseline lint/type/unit workflow. This change specifies a separate reusable workflow, `ragfence-test.yml`, rather than folding service evaluation into the existing quality job.

## Scope

- Define a reusable `workflow_call` workflow with Python 3.12 as the supported matrix entry.
- Make the execution order explicit: checkout, Python/install, `ragfence init --up`, target startup/readiness, `ragfence test --adapter <target> --threshold N --json`, JSON artifact upload, and safe PR summary/comment.
- Preserve the Phase 8/CLI exit contract: 0 passes, 1 is below threshold (and blocks the check), 2 is configuration/runtime failure.
- Make fake providers the default CI path, so identical inputs and commit state produce identical scores and canonical reports without external model credentials.
- Specify local, offline tests that parse and inspect workflow YAML; tests must not call GitHub Actions, GitHub APIs, Docker Hub, or external providers.
- Define secret-safe logging and fork-safe PR comment behavior.

## Dependencies and contracts

- Phase 8 evaluation/reporting: canonical 0–100 weighted score, deterministic JSON, redacted evidence, threshold equality passes, report written even for a completed below-threshold run.
- Phase 9 generic HTTP adapter: `--adapter generic_http`, target/base URL and health semantics, bounded evidence, no bearer token in logs or evidence.
- Phase 6 CLI: `ragfence init --up`, `ragfence test`, `--threshold`, `--json`, and exit codes 0/1/2.
- `docs/APP_FLOW.md` CI contract: unhealthy target and empty suite fail closed; fake providers are the default; optional artifact/comment are review surfaces.

## Success criteria

1. The reusable workflow structure can be validated locally from YAML without a GitHub runner.
2. The workflow runs on `pull_request` through a caller and is usable from another repository through `workflow_call` inputs.
3. Python 3.12 is represented in the matrix, with a deterministic fake-provider default and no required model secret.
4. The evaluation command's exit status is not swallowed: a score below threshold yields a failed job/check while the JSON artifact remains uploadable.
5. The report is uploaded even when evaluation returns exit 1, and a summary is written without interpolating untrusted report text into shell code.
6. PR comments are optional, idempotent, permission-minimized, and skipped for untrusted fork contexts unless the caller explicitly provides a safe permission model.
7. No workflow step prints secrets, authorization headers, DSNs, or provider payloads.

## Out of scope

- Production application, adapter, evaluator, report, or CLI implementation changes.
- Changes to `.github/workflows/ci.yml` in this artifact-authoring phase.
- Provisioning a production database or deploying a target service.
- Requiring real LLM/embedding credentials, live GitHub API calls in tests, or probabilistic judge behavior.
- Branch protection configuration itself; repository administrators must require the resulting check separately.
