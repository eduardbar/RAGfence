"""Typer command surface for RAGFence."""

from __future__ import annotations

import json
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Literal

import typer
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ragfence.cli.config import ConfigError, apply_profile, load_config
from ragfence.cli.errors import RuntimeCommandError
from ragfence.cli.report_html import render_html
from ragfence.cli.reporting import (
    find_regressions,
    load_baseline,
    render_json,
    render_text,
    write_report,
)
from ragfence.cli.seams import check_adapter, check_demo, default_report_path, evaluate
from ragfence.datasets import seed_reference_corp

app = typer.Typer(
    name="ragfence",
    help="Security testing and authorization-aware retrieval for RAG systems.",
    add_completion=False,
    no_args_is_help=True,
)
adapter_app = typer.Typer(help="Validate configured RAG adapters.")
app.add_typer(adapter_app, name="adapter")


def _reference_root() -> Path:
    """Locate the reference environment: checkout root or packaged wheel copy.

    A repository checkout keeps using its own ``alembic.ini``/``alembic``/
    ``docker-compose.yml`` at the repo root. An installed (non-editable) wheel
    falls back to the copies shipped inside ``ragfence/reference`` so the CLI
    never depends on the checkout to bootstrap the reference database.
    """
    cli_dir = Path(__file__).resolve().parent
    checkout_root = cli_dir.parents[2]
    if (checkout_root / "alembic.ini").is_file() and (checkout_root / "alembic").is_dir():
        return checkout_root
    packaged = cli_dir.parent / "reference"
    if (packaged / "docker-compose.yml").is_file() and (packaged / "alembic.ini").is_file():
        return packaged
    raise RuntimeCommandError(
        "reference environment not found; run from a repository checkout or "
        "reinstall the ragfence wheel"
    )


def bootstrap_reference(path: Path) -> None:
    """Start, migrate, and seed the bundled local pgvector reference environment.

    Idempotent: if the configured DSN already answers, docker compose is not
    invoked — an existing healthy reference database is migrated and reseeded
    in place. Compose startup happens only when the database is unreachable.
    """
    del path  # kept for signature compatibility; the environment lives in the package
    root = _reference_root()
    dsn = os.environ.get(
        "RAGFENCE_DATABASE_DSN", "postgresql+psycopg://ragfence:ragfence@localhost:5434/ragfence"
    )
    engine = create_engine(dsn, connect_args={"connect_timeout": 2})
    try:
        reachable = False
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            reachable = True
        except Exception:
            reachable = False
        if not reachable:
            try:
                subprocess.run(["docker", "compose", "up", "-d"], cwd=root, check=True, timeout=120)
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise RuntimeCommandError(
                    "could not start PostgreSQL/pgvector; install Docker Desktop and "
                    "run 'docker compose up -d'"
                ) from exc
            for _ in range(30):
                try:
                    with engine.connect() as connection:
                        connection.execute(text("SELECT 1"))
                    break
                except Exception:
                    time.sleep(1)
            else:
                raise RuntimeCommandError(
                    "PostgreSQL/pgvector did not become ready within 30 seconds"
                )
        alembic = Config(str(root / "alembic.ini"))
        alembic.set_main_option("sqlalchemy.url", dsn)
        alembic.set_main_option("script_location", str(root / "alembic"))
        command.upgrade(alembic, "head")
        with Session(engine) as session:
            seed_reference_corp(session)
    finally:
        engine.dispose()


DEFAULT_CONFIG_PATH = Path("ragfence.toml")


def _resolve_config(config: Path | None) -> tuple[Path, bool]:
    """Resolve the CLI config option to (path, was_explicitly_provided)."""
    if config is None:
        return DEFAULT_CONFIG_PATH, False
    return config, True


@app.callback()
def main() -> None:
    """RAGFence CLI — security testing and authorization-aware retrieval."""


@app.command()
def init(
    path: Path = typer.Option(Path("."), help="Project directory to initialize."),  # noqa: B008
    force: bool = typer.Option(False, help="Replace an existing configuration."),  # noqa: B008
    with_demo: bool = typer.Option(False, "--with-demo", help="Include demo settings."),  # noqa: B008
    up: bool = typer.Option(False, "--up", help="Start, migrate, and seed the local reference DB."),  # noqa: B008
) -> None:
    """Initialize a RAGFence project."""
    del with_demo
    config_path = path / "ragfence.toml"
    if config_path.exists() and not force:
        typer.echo(f"configuration already exists: {config_path}", err=True)
        raise typer.Exit(code=2)
    path.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '# RAGFence configuration\nthreshold = 0.8\nadapter = "reference"\n',
        encoding="utf-8",
    )
    (path / ".ragfence" / "reports").mkdir(parents=True, exist_ok=True)
    if up:
        try:
            bootstrap_reference(path)
        except RuntimeCommandError as exc:
            typer.echo(f"command failed: {exc}", err=True)
            raise typer.Exit(code=2) from exc
    typer.echo(f"initialized RAGFence project: {path}")


@app.command("test")
def test_command(
    config: Path | None = typer.Option(None, help="Configuration file."),  # noqa: B008
    adapter: str | None = typer.Option(None, help="Adapter name."),  # noqa: B008
    base_url: str | None = typer.Option(None, help="Target base URL."),  # noqa: B008
    threshold: float | None = typer.Option(None, help="Minimum passing score (0–1)."),  # noqa: B008
    profile: Literal["default", "strict", "permissive"] = typer.Option(
        "default",
        "--profile",
        help=(
            "Policy profile: default uses config threshold; strict forces at least 95% "
            "and requires every control to PASS; permissive caps threshold at 60%. "
            "Precedence: explicit flag > profile > config."
        ),
    ),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="Render JSON output."),  # noqa: B008
    output: Path | None = typer.Option(None, "--output", help="Explicit report destination."),  # noqa: B008
    baseline: Path | None = typer.Option(None, "--baseline", help="Previous JSON report."),  # noqa: B008
) -> None:
    """Run the configured RAGFence evaluation suite."""
    config_path, explicit_config = _resolve_config(config)
    try:
        settings = load_config(config_path, require=explicit_config)
        selected_adapter = settings.adapter if adapter is None else adapter
        if base_url is not None and selected_adapter == "generic_http":
            settings = load_config(config_path, base_url_override=base_url, require=explicit_config)
        settings = apply_profile(settings, profile)
        if threshold is not None:
            settings = settings.__class__(
                threshold=threshold,
                adapter=settings.adapter,
                generic_http=settings.generic_http,
            )
        baseline_payload = load_baseline(baseline) if baseline is not None else None
        report = evaluate(settings, adapter=adapter, base_url=base_url)
        if baseline_payload is not None:
            report.artifact["regressions"] = find_regressions(baseline_payload, report)  # type: ignore[index]
        destination = write_report(
            report,
            output or default_report_path(config_path, json_output=json_output),
            json_output=json_output,
        )
    except (ConfigError, RuntimeCommandError, RuntimeError, ValueError) as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"command failed: cannot write report: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    rendered_output = render_json(report) if json_output else render_text(report)
    typer.echo(rendered_output, nl=False)
    regressions = report.artifact.get("regressions", []) if report.artifact else []
    if regressions:
        typer.echo("Regressions:", err=True)
        for regression in regressions:
            typer.echo(
                f"REGRESSION {regression['control_id']}: "
                f"{regression['from']} -> {regression['to']}",
                err=True,
            )
    if profile == "strict":
        controls = report.artifact.get("controls", []) if report.artifact else []
        non_passing: list[str] = []
        if isinstance(controls, list):
            for control in controls:
                if not isinstance(control, dict):
                    continue
                status = control.get("status")
                status_value = getattr(status, "value", status)
                if str(status_value).upper() != "PASS":
                    non_passing.append(str(control.get("id", "unknown")))
        if non_passing:
            typer.echo(
                "strict profile failed; non-passing controls: " + ", ".join(non_passing),
                err=True,
            )
            raise typer.Exit(code=1)

    gate_passed = report.artifact.get("gate_passed") if report.artifact else None
    if gate_passed is not None:
        if not gate_passed or regressions:
            raise typer.Exit(code=1)
    elif report.score < report.threshold:
        raise typer.Exit(code=1)
    typer.echo(f"report written: {destination}", err=True)


@app.command("report")
def report_command(
    report_path: Path = typer.Argument(..., help="JSON report to view."),  # noqa: B008
    output: Path | None = typer.Option(None, "--output", help="HTML destination."),  # noqa: B008
    open_report: bool = typer.Option(
        False, "--open", help="Open the generated HTML report in a browser."
    ),  # noqa: B008
) -> None:
    """Convert a JSON report into a standalone HTML viewer."""
    try:
        try:
            raw_payload = report_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"cannot read report '{report_path}': {exc}") from exc
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid report '{report_path}': invalid JSON ({exc.msg})") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("outcome"), str):
            raise ValueError(
                f"invalid report '{report_path}': expected a JSON object with an outcome"
            )
        controls = payload.get("controls")
        if controls is not None and not isinstance(controls, list):
            raise ValueError(f"invalid report '{report_path}': controls must be a list")
        destination = output or report_path.with_suffix(".html")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_html(payload), encoding="utf-8")
    except ValueError as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except OSError as exc:
        typer.echo(f"command failed: cannot write HTML report: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    if open_report:
        webbrowser.open(destination.resolve().as_uri())
    typer.echo(f"HTML report written: {destination}")


@app.command()
def demo(
    config: Path | None = typer.Option(None, help="Configuration file."),  # noqa: B008
    up: bool = typer.Option(False, help="Start the local reference service."),  # noqa: B008
) -> None:
    """Start or inspect the local reference demo."""
    config_path, explicit_config = _resolve_config(config)
    try:
        check_demo(load_config(config_path, require=explicit_config), start=up)
    except (ConfigError, RuntimeCommandError, RuntimeError, ValueError) as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("reference demo is available")


@adapter_app.command("check")
def adapter_check(
    name: str = typer.Argument("reference", help="Adapter name to validate."),  # noqa: B008
    config: Path | None = typer.Option(None, help="Configuration file."),  # noqa: B008
    base_url: str | None = typer.Option(None, help="Target base URL."),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="Render JSON output."),  # noqa: B008
) -> None:
    """Check adapter configuration and reachability."""
    del json_output
    try:
        settings = load_config(config)
        if base_url is not None and name == "generic_http":
            settings = load_config(config, base_url_override=base_url)
        check_adapter(settings, name=name, base_url=base_url)
    except (ConfigError, RuntimeCommandError, RuntimeError, ValueError) as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"adapter available: {name}")


if __name__ == "__main__":
    app()
