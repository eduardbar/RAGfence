# Contributing to RAGFence

Thanks for contributing. This project follows a spec-driven development (SDD)
workflow: significant changes start from a proposal in `openspec/changes/` and
flow through spec, design, tasks, implementation, and verification.

## Development setup

Requires Python >= 3.12.

```console
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# source .venv/bin/activate && pip install -e ".[dev]"   # POSIX
```

## Quality gates

All gates must pass before a change is reviewable:

```console
python -m pytest          # tests
ruff check .              # lint
ruff format --check .     # formatting
mypy                      # strict type checking
```

Tests must pass **without Docker and without API keys**. Database-backed tests are
marked `@pytest.mark.db` and skip when PostgreSQL is unavailable.

## Committing

- Use Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `ci:`, ...).
- Tests ship with the behavior they verify — one work unit per commit.
- Do not add AI/Co-Authored-By attribution lines.
- Keep PRs under ~400 changed lines; larger changes are delivered as stacked PRs.

## Reporting issues

Open an issue with reproduction steps and expected vs. actual behavior.
