# Design: RAGFence CI Integration

## Technical approach

Add `.github/workflows/ragfence-test.yml` as a reusable workflow. It is intentionally orchestration-only: product behavior remains in `ragfence init`, the Phase 9 adapter, and the Phase 8 evaluation/reporting engine so local and CI invocations share the same contracts.

A small caller workflow (or a repository's existing PR workflow) invokes `workflow_call` with the target adapter and service settings. The reusable workflow owns setup and review surfaces, not scoring logic.

## Workflow contract

### Inputs

| Input | Type | Default | Meaning |
|---|---|---:|---|
| `adapter` | string | `generic_http` | Adapter passed to `ragfence test --adapter`. |
| `target` | string | `target` | Target service/compose service to start. |
| `base-url` | string | `http://127.0.0.1:8000` | Target URL passed to the adapter. |
| `threshold` | number | `80` | Canonical Phase 8 score threshold, inclusive 0–100. |
| `start-target-command` | string | documented repository default | Command to start the target; must be quoted as one workflow input and must not contain secrets. |
| `comment` | boolean | `true` | Enables the optional PR comment path when the event is trusted. |
| `fake-providers` | boolean | `true` | Explicitly selects deterministic fake embedding/LLM providers by default. |

The implementation MUST validate/normalize inputs before invoking the CLI. Secrets, if ever needed for an explicitly opted-in target, are passed through the environment and never echoed; the default path requires none.

### Job permissions and event safety

The job requests only `contents: read` and `actions: read`; `pull-requests: write` is conditional on the repository's caller opting into comments. The summary is always written using `$GITHUB_STEP_SUMMARY`. A PR comment is only attempted when all of these hold: comment input is true, the event is `pull_request` (not an untrusted `pull_request_target` execution), the head repository is the base repository, and the job has an explicit write permission. Fork PRs receive the check and artifact but no write-capable comment operation.

Do not pass report contents through `eval`, command substitution, or an unquoted shell interpolation. A summary step should parse the known JSON fields with a local Python script or `jq`, render bounded scalar fields, and use the Actions multiline environment-file protocol. Untrusted findings are treated as data.

## Ordered steps

1. **Checkout** with `actions/checkout@v4` and no persisted credential beyond the action default required for checkout.
2. **Setup Python** with `actions/setup-python@v5`, matrix value `3.12`.
3. **Install** with `python -m pip install --upgrade pip` followed by `python -m pip install -e '.[dev]'`; no credentials in the command line.
4. **Initialize/up** with `ragfence init --up`; failure stops before evaluation.
5. **Start target** using the configured target command (normally the repository's Compose target service), then run the Phase 9 health/readiness check with a finite timeout and bounded retries. A target that never becomes healthy fails closed.
6. **Evaluate** with `ragfence test --adapter "$ADAPTER" --base-url "$BASE_URL" --threshold "$THRESHOLD" --json --output .ragfence/reports/ci.json`, with fake providers selected by default. The step must preserve exit 1 and 2 in a step outcome visible to later artifact/summary steps (`continue-on-error` is allowed only when the outcome is captured and the final gate re-emits it).
7. **Upload JSON** using `actions/upload-artifact@v4`, with `if: always()` after initialization and a stable artifact name. The upload must not make a missing report look like a successful evaluation.
8. **Summary** using `if: always()` and `$GITHUB_STEP_SUMMARY`, including score, threshold, outcome, passed-threshold flag, report path, and CLI exit status. It must distinguish execution/configuration errors from a valid below-threshold result.
9. **Optional PR comment** using a least-privilege GitHub action/script only under the trusted PR guard. It should update one marker-based comment rather than create an unbounded comment stream; body fields are bounded and secret-free.
10. **Final gate** exits with the captured CLI status. 0 is green; 1 is red and blocks branch protection; 2 is red as a setup/configuration failure. Artifact and summary steps precede this gate.

## Determinism guard

The workflow sets fake provider configuration explicitly (for example `RAGFENCE_LLM_PROVIDER=fake` and `RAGFENCE_EMBEDDING_PROVIDER=fake`, using the names exposed by the product config) and avoids timestamps, random seeds, network judges, and nondeterministic report fields in the compared payload. A local verification test runs the same workflow contract twice against a fixture report and asserts identical canonical score/fingerprint fields. It does not claim two GitHub runs were executed.

The report comparison MUST ignore intentionally run-specific metadata such as artifact run ID or wall-clock timestamps, while requiring equal score, threshold, case ordering, findings ordering, and deterministic report fingerprint. The CLI/report contract remains authoritative for canonical JSON bytes and redaction.

## Local verification strategy (TDD)

Create tests under the future workflow-test location (implementation task only) that load `.github/workflows/ragfence-test.yml` with a YAML parser and inspect structure, not a GitHub runner. Tests should assert: `workflow_call`, Python 3.12 matrix, required ordered action/run steps, `ragfence init --up`, adapter/threshold/json arguments, `if: always()` artifact upload, final exit propagation, fake-provider defaults, summary marker, fork-safe comment condition, least-privilege permissions, and absence of secret-printing commands. Use a fake report and local command doubles for summary/determinism tests. No test may make HTTP requests or invoke GitHub APIs.

## Failure and security decisions

- **Fail closed:** no target health, missing suite, invalid configuration, crash, or exit 2 produces a failed check.
- **Threshold is authoritative:** equality passes; below threshold is exit 1 and must not be converted to success by `continue-on-error`.
- **Artifact preservation:** upload completed/partial JSON after evaluation failure, but never fabricate a report when initialization or evaluation produced none.
- **Secret hygiene:** use GitHub secret masking only as defense in depth; never print environment dumps, `${{ toJSON(...) }}`, headers, DSNs, tokens, or full provider responses.
- **PR safety:** never grant write permissions to an untrusted fork execution; comments are optional and marker-idempotent.
- **Current CI preservation:** this change describes a new workflow and does not alter the existing `.github/workflows/ci.yml` quality gates.

## Implementation targets

- `.github/workflows/ragfence-test.yml` — reusable workflow (later apply phase).
- `tests/test_ci_workflow_structure.py` — offline YAML structure and security assertions.
- `tests/fixtures/ci_report.json` — deterministic, redacted report fixture for summary/gate tests.
- Optional caller wiring remains a separate, explicitly reviewed workflow change; it is not required to mutate the existing baseline in this artifact phase.
