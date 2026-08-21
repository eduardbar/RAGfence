# Tasks: RAGFence Production E2E

- [x] 1. RED/GREEN: define deterministic two-tenant fixture and persisted seed coverage.
- [x] 2. RED/GREEN: wire a DB-backed reference adapter and prove allow/block paths through pgvector.
- [x] 3. RED/GREEN: add a deterministic declarative positive/negative evaluation-control matrix with canonical IDs and self-describing fixture/identity/retrieval requirements. Keep execution statuses and fail-closed gate behavior for the following dedicated work units.
- [x] 4. RED/GREEN: add explicit generic HTTP case identity representation/inconclusive behavior.
- [x] 5. RED/GREEN: implement CLI `init --up`, `test --output`, and functional demo/adapter checks.
- [x] 6. RED/GREEN: make Docker pgvector integration mandatory in repository CI and add command-contract execution tests.
- [x] 7. RED/GREEN: align README, technical docs, examples, and workflow contracts.
- [x] 8. Verify local Docker DB integration, full test/lint/type/package gates, smoke CLI, and security audit. (pip-audit + wheel build pending: tooling not installed in local venv; all other gates green)
- [x] 9. Run adversarial independent review; remediate all Critical/High findings and reverify.
