# Tasks: Acme Corp Synthetic Dataset

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700-800 total (PR 1 ~475, PR 2 ~335) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (org+corpus+checksums+unit tests) → PR 2 (loader+integration) |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Org model + corpus + checksums + security/determinism unit tests | PR 1 | `python -m pytest tests/test_datasets_org.py tests/test_datasets_security.py tests/test_datasets_determinism.py -q` | N/A - pure I/O-free; pytest is the only runtime boundary | Delete `src/ragfence/datasets/{__init__,constants,acme,checksums}.py` + 3 unit test files |
| 2 | SQLAlchemy loader + idempotence + DB-gated integration | PR 2 | `python -m pytest tests/test_datasets_loader.py tests/integration/test_datasets_seed.py -q` (DB-gated auto-skips without PG) | `docker compose up -d db`; DSN per `tests/conftest.py` `postgres_dsn` | Delete `loader.py`, revert `__init__.py` loader export, delete loader tests |

## Phase 1: PR 1 — Org model, corpus, checksums (unit, no DB)

- [x] 1.1 RED `tests/test_datasets_org.py`: two `build_acme_corp(SEED)` runs; assert 1 tenant, 5 depts, 4-tier user coverage, `user_groups` mapped, UUIDs identical (S1, S2)
- [x] 1.2 GREEN `src/ragfence/datasets/constants.py` + `acme.py`: frozen dataclass DTOs, `uuid.uuid5(NS, "acme-corp/{kind}/{slug}")` IDs, `random.Random(SEED)` content, fixed literal bodies (S1, S2)
- [x] 1.3 RED `tests/test_datasets_security.py`: `decide()` — engineering/internal denied CFO.pdf with `classification_escalation` in non-empty `reasons` (first failing rule); finance_analyst allowed; executives allow board-plan; confidential finance not-in-executives denied board-plan; board-plan `policy.department_id is None` (S4, S10-S13)
- [x] 1.4 GREEN `acme.py`: `AcmeDocument.policy` property + `context_for(email)` reusing core `DocumentACL`/`AuthorizationContext`; I/O-free (S6)
- [x] 1.5 RED `tests/test_datasets_determinism.py`: `canonical_json` byte-equal across fresh builds; checksum == golden literal, 64 lowercase hex (S5)
- [x] 1.6 GREEN `src/ragfence/datasets/checksums.py`: `canonical_json` (UTF-8, sorted keys) + lowercase `sha256_hex`; wire into `AcmeDocument.checksum` (S3)
- [x] 1.7 Strict typing: unknown classification / ACL extra field raises pydantic ValidationError (test + fix)
- [x] 1.8 `src/ragfence/datasets/__init__.py`: export `build_acme_corp`, DTOs, `SEED`; commit `feat(datasets): deterministic acme-corp org model and corpus` (PR 1 boundary)

## Phase 2: PR 2 — Loader + integration (DB-gated)

- [x] 2.1 RED `tests/test_datasets_loader.py`: `_build_row_plan` returns FK-ordered entities (tenant→dept→group→user→user_group→document→document_acl→document_chunks), natural unique keys, lowercase enum values (`ready`, `confidential`, `restricted`); board-plan dept NULL on document+acl rows (S8)
- [x] 2.2 GREEN `src/ragfence/datasets/loader.py`: `_build_row_plan` pure mapping + `seed_acme_corp(session)` get-or-create by natural key, skip-if-exists, one commit (S8, S9)
- [x] 2.3 `src/ragfence/datasets/__init__.py`: add `seed_acme_corp` export; commit `feat(datasets): idempotent SQLAlchemy acme-corp loader` (PR 2 boundary)
- [x] 2.4 `tests/integration/test_datasets_seed.py` (`@pytest.mark.db`, reuse `migrated_schema` fixture): clean seed inserts all rows without constraint violations; re-run leaves row counts unchanged; board-plan rows persist NULL dept (S8, S9)
