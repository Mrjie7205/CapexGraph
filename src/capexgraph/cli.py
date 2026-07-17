from __future__ import annotations

import sys
from datetime import date
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from capexgraph import __version__
from capexgraph.domain import RunMode
from capexgraph.workflows import create_run

app = typer.Typer(
    name="capexgraph",
    help="Evidence-first supply-chain investment research.",
    no_args_is_help=True,
)
console = Console()

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _create(mode: RunMode, subject: str, market: str, as_of: str | None) -> None:
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as error:
        raise typer.BadParameter("--as-of must use YYYY-MM-DD") from error
    run = create_run(mode, subject, market, as_of_date)
    console.print(
        Panel.fit(
            f"[bold]{run.id}[/bold]\n"
            f"mode  {run.mode.value}\n"
            f"input {run.subject}\n"
            f"date  {run.as_of_date}\n\n"
            "[dim]Research workflow scaffold saved under runs/.[/dim]",
            title="CapexGraph run created",
            border_style="yellow",
        )
    )


@app.command()
def info() -> None:
    """Show runtime information."""
    console.print(f"[bold]CapexGraph[/bold] {__version__} · evidence-first research · pre-alpha")


@app.command()
def theme(
    subject: Annotated[str, typer.Argument(help="Investment theme to research")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
) -> None:
    """Create a Theme Scan research run."""
    _create(RunMode.THEME, subject, market, as_of)


@app.command()
def anchor(
    subject: Annotated[str, typer.Argument(help="Ticker or company used as the market anchor")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
) -> None:
    """Create an Anchor Scan research run."""
    _create(RunMode.ANCHOR, subject, market, as_of)


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Run the local CapexGraph API."""
    import uvicorn

    uvicorn.run("capexgraph.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
