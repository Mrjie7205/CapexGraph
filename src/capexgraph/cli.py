from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from capexgraph import __version__
from capexgraph.domain import EvidenceKind, ResearchRun, RunMode, RunStatus
from capexgraph.providers import ProviderName
from capexgraph.reporting import render_run_report
from capexgraph.research import build_executor_for_run
from capexgraph.runtime import (
    MigrationError,
    RunStore,
    backup_database,
    database_status,
    restore_database,
    upgrade_database,
)
from capexgraph.runtime.store import state_db_path
from capexgraph.sources import SourceCaptureError, SourceDiscoveryService
from capexgraph.tools import (
    EvidencePack,
    EvidenceSourceRequest,
    TickerResolver,
    capture_market_snapshot,
    collect_evidence_for_run,
    collect_evidence_pack,
    review_run_evidence,
)
from capexgraph.tools.financials import attach_financial_metrics
from capexgraph.tracking import TrackingService, TrackingStage
from capexgraph.workflows import create_run, load_run, save_run

app = typer.Typer(
    name="capexgraph",
    help="Evidence-first supply-chain investment research.",
    no_args_is_help=True,
)
evidence_app = typer.Typer(help="Capture and review research evidence.", no_args_is_help=True)
ticker_app = typer.Typer(help="Resolve deterministic ticker identities.", no_args_is_help=True)
market_app = typer.Typer(help="Capture and inspect market snapshots.", no_args_is_help=True)
financials_app = typer.Typer(help="Import evidence-linked financial facts.", no_args_is_help=True)
tracking_app = typer.Typer(
    help="Track candidates and evaluate forward evidence.", no_args_is_help=True
)
report_app = typer.Typer(help="Render portable research reports.", no_args_is_help=True)
sources_app = typer.Typer(
    help="Discover, capture, and dismiss official-source suggestions.",
    no_args_is_help=True,
)
db_app = typer.Typer(
    help="Inspect, upgrade, back up, and restore SQLite state.",
    no_args_is_help=True,
)
app.add_typer(evidence_app, name="evidence")
app.add_typer(ticker_app, name="ticker")
app.add_typer(market_app, name="market")
app.add_typer(financials_app, name="financials")
app.add_typer(tracking_app, name="tracking")
app.add_typer(report_app, name="report")
app.add_typer(sources_app, name="sources")
app.add_typer(db_app, name="db")
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
    provider: ProviderName | None = None,
) -> None:
    if mode in {RunMode.THEME, RunMode.ANCHOR} and execute and provider is None:
        raise typer.BadParameter(
            f"{mode.value.title()} Scan execution requires --provider fixture or --provider openai"
        )
    try:
        as_of_date = date.fromisoformat(as_of) if as_of else None
    except ValueError as error:
        raise typer.BadParameter("--as-of must use YYYY-MM-DD") from error
    run = create_run(mode, subject, market, as_of_date)
    if provider is not None:
        run.manifest["model_provider"] = provider.value
        run = save_run(run)
    if execute:
        try:
            run = build_executor_for_run(run, provider=provider).execute(run.id)
        except (KeyError, ValueError, RuntimeError) as error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(1) from error
    _show_run(run, "CapexGraph run created")


@app.command()
def info() -> None:
    """Show runtime information."""
    console.print(f"[bold]CapexGraph[/bold] {__version__} · evidence-first research · alpha")


@app.command()
def theme(
    subject: Annotated[str, typer.Argument(help="Investment theme to research")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
    execute: Annotated[bool, typer.Option("--execute", "-x")] = False,
    provider: Annotated[
        ProviderName | None,
        typer.Option("--provider", help="Structured research provider: fixture or openai"),
    ] = None,
) -> None:
    """Create a Theme Scan research run."""
    _create(RunMode.THEME, subject, market, as_of, execute, provider)


@app.command()
def anchor(
    subject: Annotated[str, typer.Argument(help="Ticker or company used as the market anchor")],
    market: Annotated[str, typer.Option("--market", "-m")] = "CN",
    as_of: Annotated[str | None, typer.Option("--as-of", help="Research date: YYYY-MM-DD")] = None,
    execute: Annotated[bool, typer.Option("--execute", "-x")] = False,
    provider: Annotated[
        ProviderName | None,
        typer.Option("--provider", help="Structured research provider: fixture or openai"),
    ] = None,
) -> None:
    """Create an Anchor Scan research run."""
    _create(RunMode.ANCHOR, subject, market, as_of, execute, provider)


@app.command()
def demo() -> None:
    """Run the no-key A-share semiconductor-wafer golden case."""
    _create(
        RunMode.THEME,
        "A股半导体硅片",
        "CN",
        "2025-04-29",
        True,
        ProviderName.FIXTURE,
    )


@app.command("demo-anchor")
def demo_anchor() -> None:
    """Run the no-key 兆易创新 Anchor Scan golden case."""
    _create(
        RunMode.ANCHOR,
        "兆易创新",
        "CN",
        "2026-04-23",
        True,
        ProviderName.FIXTURE,
    )


@app.command("demo-alphabet-q2")
def demo_alphabet_q2() -> None:
    """Replay the frozen Alphabet Q2 2026 AI CapEx acceptance case."""
    _create(
        RunMode.THEME,
        "Alphabet 2026年Q2 AI资本开支传导",
        "US",
        "2026-07-22",
        True,
        ProviderName.FIXTURE,
    )


@app.command("run")
def run_command(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    until: Annotated[str | None, typer.Option("--until", help="Stop after this step key")] = None,
    attempts: Annotated[int, typer.Option("--attempts", min=1, max=10)] = 2,
    provider: Annotated[
        ProviderName | None,
        typer.Option("--provider", help="Provider override for a Theme or Anchor Scan"),
    ] = None,
) -> None:
    """Execute pending workflow steps."""
    try:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        run = build_executor_for_run(
            run,
            provider=provider,
            max_attempts=attempts,
        ).execute(run_id, until=until)
    except (KeyError, ValueError, RuntimeError) as error:
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
    provider: Annotated[
        ProviderName | None,
        typer.Option("--provider", help="Provider override for a Theme or Anchor Scan"),
    ] = None,
) -> None:
    """Resume from the latest completed checkpoint."""
    try:
        run = load_run(run_id)
        if run is None:
            raise KeyError(f"Research run not found: {run_id}")
        run = build_executor_for_run(
            run,
            provider=provider,
            max_attempts=attempts,
        ).execute(
            run_id,
            until=until,
            retry_failed=True,
        )
    except (KeyError, ValueError, RuntimeError) as error:
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


@evidence_app.command("collect")
def evidence_collect(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    url: Annotated[str, typer.Argument(help="Public HTML or PDF URL")],
    evidence_id: Annotated[str, typer.Option("--id", help="Stable evidence ID")],
    title: Annotated[str, typer.Option("--title")],
    kind: Annotated[EvidenceKind, typer.Option("--kind")] = EvidenceKind.COMPANY_DISCLOSURE,
    published_at: Annotated[str | None, typer.Option("--published-at")] = None,
    publisher: Annotated[str | None, typer.Option("--publisher")] = None,
) -> None:
    """Capture a public source and attach its hash to a run."""
    try:
        source = EvidenceSourceRequest(
            id=evidence_id,
            title=title,
            kind=kind,
            url=url,
            published_at=date.fromisoformat(published_at) if published_at else None,
            publisher=publisher,
        )
        document = collect_evidence_for_run(run_id, source)
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(
        f"[green]Captured[/green] {document.evidence.id} · "
        f"{document.byte_count} bytes · sha256 {document.evidence.source_hash}"
    )


@evidence_app.command("pack")
def evidence_pack(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, resolve_path=True)],
) -> None:
    """Capture every source in a JSON evidence pack."""
    try:
        pack = EvidencePack.model_validate_json(path.read_text(encoding="utf-8"))
        documents = collect_evidence_pack(run_id, pack)
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Captured[/green] {len(documents)} evidence sources")


@evidence_app.command("review")
def evidence_review(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    evidence_id: Annotated[str, typer.Argument(help="Evidence ID")],
    reject: Annotated[bool, typer.Option("--reject", help="Reject instead of approve")] = False,
) -> None:
    """Approve a hash-verified capture for use in grounded claims."""
    try:
        evidence = review_run_evidence(run_id, evidence_id, approved=not reject)
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"{evidence.id} · [bold]{evidence.status.value}[/bold]")


def _show_source_suggestions(items) -> None:
    table = Table(title="CapexGraph source review queue")
    table.add_column("ID")
    table.add_column("Authority")
    table.add_column("Kind")
    table.add_column("Status")
    table.add_column("Title")
    table.add_column("Provider")
    for item in items:
        table.add_row(
            item.id,
            item.authority.value,
            item.kind.value,
            item.status.value,
            item.title,
            f"{item.provider}@{item.provider_version}",
        )
    console.print(table)


@sources_app.command("discover")
def sources_discover(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    identifier: Annotated[
        str | None,
        typer.Option("--identifier", "-i", help="Exact SEC ticker, company name, or CIK"),
    ] = None,
    form: Annotated[
        list[str] | None,
        typer.Option("--form", help="SEC form to include; repeat for multiple forms"),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1, max=100)] = 10,
) -> None:
    """Discover recent official SEC filings as suggestions."""
    try:
        items = SourceDiscoveryService().discover(
            run_id,
            identifier=identifier,
            forms=form or (),
            limit=limit,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions(items)


@sources_app.command("add")
def sources_add(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    url: Annotated[str, typer.Argument(help="Public issuer or regulator URL")],
    title: Annotated[str, typer.Option("--title")],
    kind: Annotated[EvidenceKind, typer.Option("--kind")] = EvidenceKind.COMPANY_DISCLOSURE,
    publisher: Annotated[str | None, typer.Option("--publisher")] = None,
    published_at: Annotated[str | None, typer.Option("--published-at")] = None,
    issuer_domain: Annotated[
        list[str] | None,
        typer.Option("--issuer-domain", help="Known issuer domain; repeat as needed"),
    ] = None,
) -> None:
    """Add a user-supplied URL to the suggestion queue without capturing it."""
    try:
        item = SourceDiscoveryService().suggest_url(
            run_id,
            url=url,
            title=title,
            kind=kind,
            publisher=publisher,
            published_at=date.fromisoformat(published_at) if published_at else None,
            issuer_domains=issuer_domain or (),
        )
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions([item])


@sources_app.command("list")
def sources_list(run_id: Annotated[str, typer.Argument(help="Research run ID")]) -> None:
    """List the persisted source suggestion and capture queue."""
    try:
        items = SourceDiscoveryService().list(run_id)
    except KeyError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions(items)


@sources_app.command("capture")
def sources_capture(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion ID")],
) -> None:
    """Download one suggestion and create captured evidence if it is unique."""
    try:
        item = SourceDiscoveryService().capture(run_id, suggestion_id)
    except (KeyError, ValueError, SourceCaptureError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions([item])


@sources_app.command("retry")
def sources_retry(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion ID")],
) -> None:
    """Retry a persisted failed source capture."""
    try:
        item = SourceDiscoveryService().retry(run_id, suggestion_id)
    except (KeyError, ValueError, SourceCaptureError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions([item])


@sources_app.command("dismiss")
def sources_dismiss(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    suggestion_id: Annotated[str, typer.Argument(help="Suggestion ID")],
) -> None:
    """Dismiss one uncaptured suggestion."""
    try:
        item = SourceDiscoveryService().dismiss(run_id, suggestion_id)
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    _show_source_suggestions([item])


@ticker_app.command("resolve")
def ticker_resolve(query: Annotated[str, typer.Argument(help="Ticker, name, or alias")]) -> None:
    """Resolve a canonical, registry-backed ticker identity."""
    try:
        identity = TickerResolver().resolve(query)
    except KeyError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print_json(data=identity.model_dump(mode="json"))


@market_app.command("snapshot")
def market_snapshot(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    ticker: Annotated[str, typer.Argument(help="Ticker or registered company name")],
) -> None:
    """Fetch adjusted daily history and attach a market snapshot to a run."""
    try:
        snapshot = capture_market_snapshot(run_id, ticker)
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print_json(data=snapshot.model_dump(mode="json"))


@financials_app.command("import")
def financials_import(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, resolve_path=True)],
) -> None:
    """Import normalized, evidence-linked financial metrics from CSV."""
    try:
        metrics = attach_financial_metrics(run_id, path)
    except (KeyError, ValueError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Imported[/green] {len(metrics)} financial metrics")


@tracking_app.command("add")
def tracking_add(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    node_id: Annotated[str, typer.Argument(help="Candidate node ID")],
    benchmark: Annotated[str, typer.Option("--benchmark")] = "000300.SH",
    price: Annotated[float | None, typer.Option("--price", min=0.000001)] = None,
    benchmark_price: Annotated[
        float | None, typer.Option("--benchmark-price", min=0.000001)
    ] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    no_live: Annotated[bool, typer.Option("--no-live")] = False,
) -> None:
    """Add one run candidate to forward tracking."""
    try:
        item = TrackingService().track_run_candidate(
            run_id,
            node_id,
            benchmark_ticker=benchmark,
            call_date=date.fromisoformat(as_of) if as_of else None,
            call_price=price,
            call_benchmark_price=benchmark_price,
            capture_live=not no_live,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Tracking[/green] {item.id} · {item.ticker} vs {item.benchmark_ticker}")


@tracking_app.command("snapshot")
def tracking_snapshot(
    tracked_id: Annotated[str, typer.Argument(help="Tracked candidate ID")],
    price: Annotated[float | None, typer.Option("--price", min=0.000001)] = None,
    benchmark_price: Annotated[
        float | None, typer.Option("--benchmark-price", min=0.000001)
    ] = None,
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
    live: Annotated[bool, typer.Option("--live")] = False,
) -> None:
    """Capture a live or manual candidate/benchmark price pair."""
    service = TrackingService()
    try:
        if live:
            snapshot = service.capture_live_snapshot(tracked_id)
        else:
            if price is None or benchmark_price is None:
                raise ValueError("Manual snapshot requires --price and --benchmark-price")
            snapshot = service.add_snapshot(
                tracked_id,
                as_of_date=date.fromisoformat(as_of) if as_of else date.today(),
                price=price,
                benchmark_price=benchmark_price,
            )
    except (KeyError, ValueError, RuntimeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print_json(data=snapshot.model_dump(mode="json"))


@tracking_app.command("list")
def tracking_list() -> None:
    """Show forward scorecards with since-call alpha."""
    table = Table(title="CapexGraph tracking scorecard")
    table.add_column("ID")
    table.add_column("Ticker")
    table.add_column("Stage")
    table.add_column("Return")
    table.add_column("Benchmark")
    table.add_column("Alpha")
    table.add_column("Events")
    for card in TrackingService().scoreboard():
        latest = card.latest
        table.add_row(
            card.tracked.id,
            card.tracked.ticker,
            card.tracked.stage.value,
            f"{latest.return_pct:+.2f}%" if latest else "—",
            f"{latest.benchmark_return_pct:+.2f}%" if latest else "—",
            f"{latest.alpha_pct:+.2f}%" if latest else "—",
            str(len(card.events)),
        )
    console.print(table)


@tracking_app.command("stage")
def tracking_stage(
    tracked_id: Annotated[str, typer.Argument()],
    stage: Annotated[TrackingStage, typer.Argument()],
) -> None:
    """Move a candidate across the research stage board."""
    try:
        item = TrackingService().store.update_stage(tracked_id, stage)
    except KeyError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"{item.id} · [bold]{item.stage.value}[/bold]")


@tracking_app.command("ack")
def tracking_ack(event_id: Annotated[int, typer.Argument(min=1)]) -> None:
    """Acknowledge a fired structured trigger."""
    try:
        event = TrackingService().store.acknowledge_event(event_id)
    except KeyError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"Acknowledged event {event.id} at {event.acknowledged_at}")


@report_app.command("render")
def report_render(
    run_id: Annotated[str, typer.Argument(help="Research run ID")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Render a self-contained HTML research report."""
    try:
        path = render_run_report(run_id, output)
    except KeyError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Rendered[/green] {path}")


@db_app.command("status")
def db_status(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Database path; defaults to the active workspace"),
    ] = None,
) -> None:
    """Show the current and latest persisted schema versions."""
    target = (path or state_db_path()).resolve()
    try:
        status = database_status(target)
    except MigrationError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    pending = ", ".join(str(item) for item in status.pending_versions) or "none"
    console.print(
        Panel.fit(
            f"path       {status.path}\n"
            f"exists     {status.exists}\n"
            f"legacy     {status.legacy}\n"
            f"current    {status.current_version}\n"
            f"latest     {status.latest_version}\n"
            f"pending    {pending}",
            title="CapexGraph database",
            border_style="green" if status.up_to_date else "yellow",
        )
    )


@db_app.command("upgrade")
def db_upgrade(
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Database path; defaults to the active workspace"),
    ] = None,
) -> None:
    """Apply pending versioned migrations transactionally."""
    target = (path or state_db_path()).resolve()
    try:
        status = upgrade_database(target)
    except MigrationError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(
        f"[green]Database ready[/green] {status.path} · schema {status.current_version}"
    )


@db_app.command("backup")
def db_backup(
    output: Annotated[Path, typer.Option("--output", "-o", resolve_path=True)],
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Database path; defaults to the active workspace"),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing backup")] = False,
) -> None:
    """Create a consistent SQLite backup."""
    source = (path or state_db_path()).resolve()
    try:
        result = backup_database(source, output, overwrite=force)
    except (FileNotFoundError, FileExistsError, ValueError, MigrationError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Backup created[/green] {result}")


@db_app.command("restore")
def db_restore(
    backup: Annotated[Path, typer.Argument(exists=True, dir_okay=False, resolve_path=True)],
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Database path; defaults to the active workspace"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace the target database after stopping the API"),
    ] = False,
) -> None:
    """Restore a verified backup and bring it to the current schema."""
    target = (path or state_db_path()).resolve()
    try:
        result = restore_database(backup, target, overwrite=force)
    except (FileNotFoundError, FileExistsError, ValueError, MigrationError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"[green]Database restored[/green] {result}")


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
