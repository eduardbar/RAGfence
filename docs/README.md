# RAGFence documentation

These documents describe the v0.1 contracts. `TRD.md` is the technical source of truth for canonical model and adapter names.

- [Product requirements](PRD.md)
- [Technical requirements](TRD.md)
- [Application flow](APP_FLOW.md)
- [Backend schema](BACKEND_SCHEMA.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [UI/UX design brief](UI_UX_DESIGN_BRIEF.md)

## Release contract

- Supported Python: **3.12+**; package version: **0.1.0**.
- The supported external adapter is `generic_http`, implemented by `GenericHTTPAdapter`.
- `ragfence test` writes `.ragfence/reports/latest.txt`; `--json` writes `.ragfence/reports/latest.json`.
- Exit code **0** means the score meets the threshold; **1** means a completed run is below threshold; **2** means configuration, usage, reachability, or runtime failure.
- Offline checks use fake providers and do not require Docker, PostgreSQL, API keys, or network access. Docker Compose/PostgreSQL + pgvector is optional and only required for database-backed reference checks.
