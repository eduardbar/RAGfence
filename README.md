# RAGFence

Security testing and authorization-aware retrieval for production RAG systems.

RAGFence is a Python library and CLI that helps teams build and verify RAG
pipelines that never leak. It ships an authorization-aware reference
implementation (PostgreSQL + pgvector, deny-by-default ACL policies, authorization
before retrieval) and an adversarial evaluation harness that runs attack scenarios
against any target — the reference implementation or an external RAG system via a
thin adapter.

> **Status: foundation bootstrap.** This slice ships the installable package
> skeleton, tooling gates (Ruff, mypy, pytest), the `ragfence` CLI stub, local
> services definition, and release basics. Core domain models, the policy engine,
> and the storage schema land in the next delivery slices.

## Quickstart (development)

Requires Python >= 3.12. No external services or API keys are needed for the test
suite.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # POSIX
```

Run the quality gates:

```console
python -m pytest          # tests
ruff check .              # lint
ruff format --check .     # formatting
mypy                      # strict type checking
```

Optional — start the local PostgreSQL 16 + pgvector instance used by the
reference implementation:

```console
docker compose up -d
```

The CLI is a stub at this stage; `ragfence --help` prints usage:

```console
ragfence --help
```

## Documentation

| Doc | Contents |
|-----|----------|
| `docs/PRD.md` | Product requirements |
| `docs/TRD.md` | Technical requirements and architecture |
| `docs/BACKEND_SCHEMA.md` | Database schema reference |
| `docs/IMPLEMENTATION_PLAN.md` | Phased delivery plan |
| `CONTRIBUTING.md` | Contribution guidelines |

## License

Apache License 2.0. See [LICENSE](LICENSE).
