from __future__ import annotations

import sys
from datetime import date
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from capexgraph import __version__
from capexgraph.domain import ResearchRun, RunMode, RunStatus
from capexgraph.runtime import RunStore, WorkflowExecutor
from capexgraph.workflows import create_run, load_run

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


def _show_run(run: ResearchRun, title: str = "CapexGraph run") -> None:
    completed = sum(step.status.value == "completed" for step in run.pipeline)
    console.print(
        Panel.fit(
            f"[bold]{run.id}[/bold]\n"
            f"mode     {run.mode.value}\n"
            f"input    {run.subject}\n"
            f"date     {run.as_of_date}\n"
            f"status   {run.status.value}\n"
            f"progress {completed}/{len(run.pipeline)}",
            title=title,
            border_style="yellow" if run.status != RunStatus.FAILED else "red",
        )
    )


def _create(
    mode: RunMode,
    subject: str,
    market: str,
    as_of: str | None,
    execute: bool,
) -> None:
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as error:
        raise typer.BadParameter("--as-of must use YYYY-MM-DD") from error
    run = create_run(mode, subject, market, as_of_date)
    if execute:
        run = WorkflowExecutor().execute(run.id)
    _show_run(run, "CapexGraph run created")


@app.command()
def info() -> None:
    """Show runtime information."""
    console.print(f"[bold]CapexGraph[/bold] {__version__} · evidence-first research · pre-alpha")


@app.command()
def theme(
    subject: Annotated[str, typer.Argument(help="Investment theme to research")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
    execute: Annotated[bool, typer.Option("--execute", "-x")] = False,
) -> None:
    """Create a Theme Scan research run."""
    _create(RunMode.THEME, subject, market, as_of, execute)


@app.command()
def anchor(
    subject: Annotated[str, typer.Argument(help="Ticker or company used as the market anchor")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
    execute: Annotated[bool, typer.Option("--execute", "-x")] = False,
) -> None:
    """Create an Anchor Scan research run."""
    _create(RunMode.ANCHOR, subject, market, as_of, execute)


@app.command("run")
def run_command(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    until: Annotated[str | None, typer.Option("--until", help="Stop after this step key")] = None,
    attempts: Annotated[int, typer.Option("--attempts", min=1, max=10)] = 2,
) -> None:
    """Execute pending workflow steps."""
    try:
        run = WorkflowExecutor(max_attempts=attempts).execute(run_id, until=until)
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_run(run, "Workflow execution")
    if run.status == RunStatus.FAILED:
        raise typer.Exit(1)


@app.command()
def resume(
    run_id: Annotated[str, typer.Argument(help="Failed or interrupted research run ID")],
    until: Annotated[str | None, typer.Option("--until", help="Stop after this step key")] = None,
    attempts: Annotated[int, typer.Option("--attempts", min=1, max=10)] = 2,
) -> None:
    """Resume from the latest completed checkpoint."""
    try:
        run = WorkflowExecutor(max_attempts=attempts).execute(
            run_id,
            until=until,
            retry_failed=True,
        )
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_run(run, "Workflow resumed")
    if run.status == RunStatus.FAILED:
        raise typer.Exit(1)


@app.command("runs")
def list_run_command(
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 20,
    status: Annotated[RunStatus | None, typer.Option("--status")] = None,
) -> None:
    """List persisted research runs."""
    rows = RunStore().list_runs(limit=limit, status=status)
    table = Table(title="CapexGraph research runs")
    table.add_column("Run ID", style="bold")
    table.add_column("Mode")
    table.add_column("Subject")
    table.add_column("Market")
    table.add_column("Status")
    table.add_column("Updated")
    for run in rows:
        table.add_row(
            run.id,
            run.mode.value,
            run.subject,
            run.market,
            run.status.value,
            run.updated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@app.command()
def show(run_id: Annotated[str, typer.Argument(help="Research run ID")]) -> None:
    """Show one persisted research run."""
    run = load_run(run_id)
    if run is None:
        console.print(f"[red]Research run not found: {run_id}[/red]")
        raise typer.Exit(1)
    _show_run(run)


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
