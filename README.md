# RAGFence

Security testing and authorization-aware retrieval for production RAG systems.

RAGFence is a Python library and CLI that helps teams build and verify RAG
pipelines that never leak. It provides authorization-aware retrieval primitives,
a deterministic evaluation engine, and the `generic_http` adapter for testing an
external RAG target.

> **Status: v0.1 release candidate.** The evaluation and adapter contracts are
> implemented and covered by offline tests. The reference database path is an
> optional Docker-backed check; this repository does not claim a public CI run.

## Quickstart (offline)

Requires Python >= 3.12. The offline quickstart needs no Docker, PostgreSQL,
network access, API keys, or other external services.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # POSIX
```

Check the installed CLI, initialize a local project, and run the deterministic
reference evaluation:

```console
ragfence --help
ragfence init
ragfence test
```

The human-readable report is written to `.ragfence/reports/latest.txt` and the
machine-readable report is written with:

```console
ragfence test --json
```

which writes `.ragfence/reports/latest.json`. Exit codes are:

- **0 =** completed evaluation meets the configured threshold.
- **1 =** completed evaluation is below the threshold.
- **2 =** configuration, usage, reachability, or runtime failure.

Run the repository quality gates without Docker or other external services:

```console
python -m pytest
ruff check .
ruff format --check .
mypy
```

### Optional Docker database checks

Docker Compose is optional and only needed for database-backed reference checks.
It starts PostgreSQL 16 with pgvector; it is not required by the offline tests
or the generic HTTP adapter tests:

```console
docker compose up -d
```

Safe starting points for configuration are [`examples/reference.toml`](examples/reference.toml)
and [`examples/generic_http.toml`](examples/generic_http.toml). The latter uses
`CHANGEME` and `localhost` placeholders only.

## Documentation

See the [documentation index](docs/README.md) for the product, technical,
application-flow, schema, implementation-plan, and UI/UX documents.

- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Changelog](CHANGELOG.md)

## License

Apache License 2.0. See [LICENSE](LICENSE).
