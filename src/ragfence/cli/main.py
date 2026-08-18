"""Typer command surface for RAGFence."""

from __future__ import annotations

from pathlib import Path

import typer

from ragfence.cli.config import ConfigError, load_config
from ragfence.cli.errors import RuntimeCommandError
from ragfence.cli.reporting import render_json, render_text, write_report
from ragfence.cli.seams import check_adapter, check_demo, default_report_path, evaluate

app = typer.Typer(
    name="ragfence",
    help="Security testing and authorization-aware retrieval for RAG systems.",
    add_completion=False,
    no_args_is_help=True,
)
adapter_app = typer.Typer(help="Validate configured RAG adapters.")
app.add_typer(adapter_app, name="adapter")


@app.callback()
def main() -> None:
    """RAGFence CLI — security testing and authorization-aware retrieval."""


@app.command()
def init(
    path: Path = typer.Option(Path("."), help="Project directory to initialize."),  # noqa: B008
    force: bool = typer.Option(False, help="Replace an existing configuration."),  # noqa: B008
    with_demo: bool = typer.Option(False, "--with-demo", help="Include demo settings."),  # noqa: B008
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
    typer.echo(f"initialized RAGFence project: {path}")


@app.command("test")
def test_command(
    config: Path = typer.Option(Path("ragfence.toml"), help="Configuration file."),  # noqa: B008
    adapter: str | None = typer.Option(None, help="Adapter name."),  # noqa: B008
    base_url: str | None = typer.Option(None, help="Target base URL."),  # noqa: B008
    threshold: float | None = typer.Option(None, help="Minimum passing score."),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="Render JSON output."),  # noqa: B008
) -> None:
    """Run the configured RAGFence evaluation suite."""
    try:
        settings = load_config(config)
        selected_adapter = settings.adapter if adapter is None else adapter
        if base_url is not None and selected_adapter == "generic_http":
            settings = load_config(config, base_url_override=base_url)
        if threshold is not None:
            settings = settings.__class__(
                threshold=threshold,
                adapter=settings.adapter,
                generic_http=settings.generic_http,
            )
        report = evaluate(settings, adapter=adapter, base_url=base_url)
        destination = write_report(
            report,
            default_report_path(config, json_output=json_output),
            json_output=json_output,
        )
    except (ConfigError, RuntimeCommandError, RuntimeError, ValueError) as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    output = render_json(report) if json_output else render_text(report)
    typer.echo(output, nl=False)
    if report.score < report.threshold:
        raise typer.Exit(code=1)
    typer.echo(f"report written: {destination}", err=True)


@app.command()
def demo(
    config: Path = typer.Option(Path("ragfence.toml"), help="Configuration file."),  # noqa: B008
    up: bool = typer.Option(False, help="Start the local reference service."),  # noqa: B008
) -> None:
    """Start or inspect the local reference demo."""
    try:
        check_demo(load_config(config), start=up)
    except (ConfigError, RuntimeCommandError, RuntimeError, ValueError) as exc:
        typer.echo(f"command failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo("reference demo is available")


@adapter_app.command("check")
def adapter_check(
    name: str = typer.Argument("reference", help="Adapter name to validate."),  # noqa: B008
    config: Path = typer.Option(Path("ragfence.toml"), help="Configuration file."),  # noqa: B008
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
