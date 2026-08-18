# Delta for project-bootstrap

## ADDED Requirements

### Requirement: Packaging Contract

The project MUST ship a `pyproject.toml` that is uv-compatible, uses a `src/` layout (`src/ragfence/`), declares `requires-python >=3.12`, and defines a `ragfence` console entry point.

#### Scenario: Editable install and import

- GIVEN a clean virtual environment
- WHEN `pip install -e .` succeeds and `import ragfence` runs
- THEN the import succeeds without error
- AND the `ragfence` console script is available on PATH

### Requirement: CLI Stub

The `ragfence` command MUST provide a working `--help` that exits 0 and prints usage text.

#### Scenario: Help exit code

- GIVEN the package installed
- WHEN `ragfence --help` is run
- THEN the process exits with code 0
- AND usage output is printed

### Requirement: Tooling Configuration

`pyproject.toml` MUST configure Ruff (lint and format), mypy strict, and pytest so that `ruff check`, `ruff format --check`, `mypy`, and `python -m pytest` run from a fresh checkout without Docker.

#### Scenario: Quality gates pass without Docker

- GIVEN a fresh checkout with dependencies installed
- WHEN `python -m pytest` and `mypy` are run
- THEN the test suite is green
- AND no type errors are reported

### Requirement: Local Services

`docker-compose.yml` MUST define a PostgreSQL 16 service using the pinned `pgvector/pgvector:pg16` image with a healthcheck and a host port mapping.

#### Scenario: Compose config valid

- GIVEN the repository root
- WHEN `docker compose config` is run
- THEN the file parses without errors
- AND the service declares image `pgvector/pgvector:pg16`

### Requirement: Continuous Integration

`.github/workflows/ci.yml` MUST run Ruff check, Ruff format check, mypy strict, and `python -m pytest` on Python 3.12 on every push and pull request.

#### Scenario: CI matrix

- GIVEN a workflow run
- WHEN the matrix executes
- THEN the job runs on Python 3.12
- AND every gate must pass for the job to be green

### Requirement: Release Basics

The repository MUST include an Apache-2.0 `LICENSE`, a `README.md`, a `CONTRIBUTING.md` stub, and a `.env.example` containing placeholders only; it MUST NOT contain real credentials.

#### Scenario: No secrets in template

- GIVEN the committed `.env.example`
- WHEN its values are inspected
- THEN every value is a placeholder
- AND no real token, key, or password is present

## Decisions

- CI matrix: Python 3.12 only for this change (extend later). Rationale: pinned compatible versions mitigate the 3.14 wheel-gap risk; local dev still runs 3.14.5.
- Local services: pin `pgvector/pgvector:pg16`. Rationale: stable, widely used PG16 + pgvector image.
- License: Apache-2.0 (decided in sdd-init).
