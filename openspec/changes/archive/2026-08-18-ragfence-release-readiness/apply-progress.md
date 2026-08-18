# Apply progress: Work Units 6–9

## Work Unit 6 — Acme performance sanity

- Added `src/ragfence/release_readiness/benchmark.py` and a focused test.
- The benchmark uses the deterministic Acme fixture and fake embedding provider only; it does not make network/provider calls.
- Frozen baseline is explicitly a `local_sanity_baseline` with a 500 ms search p95 regression budget. It is marked `production_claim: false` and is not a production capacity claim.
- Evidence fields include environment, corpus/query/repetition counts, setup time, search p50/p95, errors, and unauthorized retrieval count.

## Work Unit 7 — Offline CI and secret safety

- Added offline checks covering both `.github/workflows/ci.yml` and `.github/workflows/ragfence-test.yml`.
- Existing workflow structure/security tests plus the release checklist assert ordered quality/evaluation gates, fake providers, artifact/summary/final-gate behavior, and no secret-printing commands.
- No GitHub API, runner, external target, or public-CI receipt was invoked.

## Work Unit 8 — Dependency and secret audit

- Added `src/ragfence/release_readiness/audit.py`.
- Scopes: tracked text, reachable Git history, `uv.lock`, and wheel text contents.
- Secret-shaped findings contain scope/kind only; secret values are never returned. Local test/placeholder DSNs and fake tokens are recognized as non-secret fixtures.
- Local `uv audit` completed with status `clean`; output is intentionally suppressed. No `pip-audit` fallback was needed.

## Work Unit 9 — Release checklist

- Added `src/ragfence/release_readiness/checklist.py`.
- Checklist returns `release_ready: false` when the public CI receipt is absent and classifies that condition as `blocked_non_local`; it explicitly records that local results are not substituted.
- Local offline, benchmark, and audit checks are independently reported.

## Verification

- `RAGFENCE_TEST_DATABASE_DSN=...localhost:5434/ragfence uv run pytest -q`: **408 passed, 0 skipped**.
- Release/readiness focused tests: **16 passed**.
- `ruff check` on release-readiness code/tests: **passed**.
- `ruff format --check` on release-readiness code/tests: **passed**.
- `mypy src/ragfence/release_readiness`: **Success: no issues found in 4 source files**.
- `release_ready: true` after satisfying the public CI receipt gate.
- Public CI receipt obtained after publication: `https://github.com/eduardbar/RAGfence/actions/runs/32184780731`, commit `90331b56f3b93d4bda371deeacdfa8aa312087eb`, workflow `CI`, conclusion `success`.
- Release checklist now returns `release_ready: true` with the public receipt.
- Deployment was not performed.
