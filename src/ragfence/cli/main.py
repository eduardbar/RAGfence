"""Typer command surface for RAGFence."""

import typer

app = typer.Typer(
    name="ragfence",
    help="Security testing and authorization-aware retrieval for RAG systems.",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """RAGFence CLI — security testing and authorization-aware retrieval."""


if __name__ == "__main__":
    app()
