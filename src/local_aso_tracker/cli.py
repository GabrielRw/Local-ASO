"""Typer command-line interface for Local ASO Tracker."""

from __future__ import annotations

import logging
import webbrowser
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from local_aso_tracker.config import (
    database_path,
    load_settings,
    validate_country_code,
    write_default_config,
)
from local_aso_tracker.database import run_migrations, session_scope
from local_aso_tracker.models import App, Keyword, RankCheck, Storefront, TrackingTarget
from local_aso_tracker.reports.exports import export_history_csv, export_json, export_latest_csv
from local_aso_tracker.reports.html import generate_html_report
from local_aso_tracker.repositories.data import (
    INITIAL_COUNTRIES,
    add_app,
    add_keyword,
    add_storefront,
    add_target,
    filter_missing_today,
    latest_pairs,
    list_targets,
    normalize_keyword,
    parse_date_start,
    seed_catalog,
    seed_targets,
    successful_checks,
)
from local_aso_tracker.services.analytics import (
    RankingRow,
    calculate_summary,
    opportunity_group,
)
from local_aso_tracker.services.checks import run_checks
from local_aso_tracker.utils.logging import configure_logging

app = typer.Typer(
    name="aso", no_args_is_help=True, help="Track App Store search visibility locally."
)
apps_app = typer.Typer(no_args_is_help=True, help="Manage tracked iOS apps.")
keywords_app = typer.Typer(no_args_is_help=True, help="Manage keywords.")
countries_app = typer.Typer(no_args_is_help=True, help="Manage storefront countries.")
track_app = typer.Typer(no_args_is_help=True, help="Manage app/keyword/storefront targets.")
export_app = typer.Typer(no_args_is_help=True, help="Export local ranking data.")
app.add_typer(apps_app, name="apps")
app.add_typer(keywords_app, name="keywords")
app.add_typer(countries_app, name="countries")
app.add_typer(track_app, name="track")
app.add_typer(export_app, name="export")

console = Console()
error_console = Console(stderr=True)
quiet_mode = False


@app.callback()
def root(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show diagnostic console logs."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
) -> None:
    """Configure output and local rotating logs."""

    global quiet_mode
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be used together")
    quiet_mode = quiet
    configure_logging(verbose=verbose, quiet=quiet)


def emit(message: str, *, style: str | None = None) -> None:
    if not quiet_mode:
        console.print(message, style=style)


def require_initialized() -> None:
    if not database_path().exists():
        raise typer.BadParameter("database is not initialized; run 'aso init' first")


def local_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def print_table(table: Table) -> None:
    if not quiet_mode:
        console.print(table)


@app.command("init")
def initialize(
    seed: bool = typer.Option(False, "--seed", help="Seed AstroLingo and all initial targets."),
) -> None:
    """Create the local configuration and migrate the SQLite database."""

    try:
        path = write_default_config()
        run_migrations()
        created_targets = 0
        counts = {"apps": 0, "countries": 0, "keywords": 0}
        if seed:
            with session_scope() as session:
                counts = seed_catalog(session)
                created_targets = seed_targets(session)
        emit(f"[green]Ready.[/] Database: {database_path()}")
        emit(f"Config: {path}")
        if seed:
            emit(
                "Seeded "
                f"{counts['apps']} new app(s), {counts['countries']} new countries, "
                f"{counts['keywords']} new keywords, and {created_targets} new targets."
            )
    except Exception as exc:
        logging.getLogger(__name__).debug("Initialization failed", exc_info=True)
        raise typer.BadParameter(f"database migration or initialization failed: {exc}") from exc


@apps_app.command("list")
def apps_list() -> None:
    require_initialized()
    with session_scope() as session:
        items = session.scalars(select(App).order_by(App.name)).all()
        table = Table("Name", "Apple ID", "Bundle ID", "Status", title="Apps")
        for item in items:
            table.add_row(
                item.name,
                str(item.apple_app_id),
                item.bundle_id or "—",
                "active" if item.active else "inactive",
            )
        print_table(table)


@apps_app.command("add")
def apps_add(
    name: str = typer.Option(..., "--name"),
    apple_id: int = typer.Option(..., "--apple-id"),
    bundle_id: str | None = typer.Option(None, "--bundle-id"),
) -> None:
    require_initialized()
    if apple_id <= 0 or not name.strip():
        raise typer.BadParameter("name and a positive numerical Apple ID are required")
    with session_scope() as session:
        item, created = add_app(session, name, apple_id, bundle_id)
        emit(f"{'Added' if created else 'Already exists'}: {item.name} ({item.apple_app_id})")


def _set_app_active(apple_id: int, active: bool) -> None:
    require_initialized()
    with session_scope() as session:
        item = session.scalar(select(App).where(App.apple_app_id == apple_id))
        if item is None:
            raise typer.BadParameter(f"unknown app ID: {apple_id}")
        item.active = active
        emit(f"{item.name} is now {'active' if active else 'inactive'}; history was preserved.")


@apps_app.command("remove")
def apps_remove(apple_id: int) -> None:
    """Soft-remove an app while preserving history."""
    _set_app_active(apple_id, False)


@apps_app.command("activate")
def apps_activate(apple_id: int) -> None:
    _set_app_active(apple_id, True)


@apps_app.command("deactivate")
def apps_deactivate(apple_id: int) -> None:
    _set_app_active(apple_id, False)


@keywords_app.command("list")
def keywords_list() -> None:
    require_initialized()
    with session_scope() as session:
        items = session.scalars(select(Keyword).order_by(Keyword.keyword)).all()
        table = Table("Keyword", "Normalized", "Status", title="Keywords")
        for item in items:
            table.add_row(
                item.keyword, item.normalized_keyword, "active" if item.active else "inactive"
            )
        print_table(table)


@keywords_app.command("add")
def keywords_add(keyword: str) -> None:
    require_initialized()
    with session_scope() as session:
        item, created = add_keyword(session, keyword)
        emit(f"{'Added' if created else 'Duplicate ignored'}: {item.keyword}")


@keywords_app.command("add-file")
def keywords_add_file(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    require_initialized()
    added = duplicates = 0
    with session_scope() as session:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            _, created = add_keyword(session, line)
            added += int(created)
            duplicates += int(not created)
    emit(f"Added {added} keyword(s); ignored {duplicates} duplicate(s).")


def _set_keyword_active(keyword: str, active: bool) -> None:
    require_initialized()
    with session_scope() as session:
        item = session.scalar(
            select(Keyword).where(Keyword.normalized_keyword == normalize_keyword(keyword))
        )
        if item is None:
            raise typer.BadParameter(f"unknown keyword: {keyword}")
        item.active = active
        emit(
            f"'{item.keyword}' is now {'active' if active else 'inactive'}; history was preserved."
        )


@keywords_app.command("remove")
def keywords_remove(keyword: str) -> None:
    _set_keyword_active(keyword, False)


@keywords_app.command("activate")
def keywords_activate(keyword: str) -> None:
    _set_keyword_active(keyword, True)


@keywords_app.command("deactivate")
def keywords_deactivate(keyword: str) -> None:
    _set_keyword_active(keyword, False)


@countries_app.command("list")
def countries_list() -> None:
    require_initialized()
    with session_scope() as session:
        items = session.scalars(select(Storefront).order_by(Storefront.country_code)).all()
        table = Table("Code", "Storefront", "Status", title="Countries")
        for item in items:
            table.add_row(
                item.country_code, item.display_name, "active" if item.active else "inactive"
            )
        print_table(table)


@countries_app.command("add")
def countries_add(code: str, display_name: str) -> None:
    require_initialized()
    with session_scope() as session:
        item, created = add_storefront(session, code, display_name)
        emit(
            f"{'Added' if created else 'Already exists'}: {item.country_code} — {item.display_name}"
        )


def _set_country_active(code: str, active: bool) -> None:
    require_initialized()
    try:
        normalized = validate_country_code(code)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with session_scope() as session:
        item = session.scalar(select(Storefront).where(Storefront.country_code == normalized))
        if item is None:
            raise typer.BadParameter(f"unknown country: {normalized}")
        item.active = active
        emit(f"{normalized} is now {'active' if active else 'inactive'}; history was preserved.")


@countries_app.command("remove")
def countries_remove(code: str) -> None:
    _set_country_active(code, False)


@countries_app.command("activate")
def countries_activate(code: str) -> None:
    _set_country_active(code, True)


@countries_app.command("deactivate")
def countries_deactivate(code: str) -> None:
    _set_country_active(code, False)


@track_app.command("add")
def track_add(
    app_id: int = typer.Option(..., "--app-id"),
    keyword: str = typer.Option(..., "--keyword"),
    country: str = typer.Option(..., "--country"),
    device: str = typer.Option("iphone", "--device"),
) -> None:
    require_initialized()
    with session_scope() as session:
        target, created = add_target(session, app_id, keyword, country, device)
        emit(f"{'Added' if created else 'Already tracked'} target #{target.id}.")


@track_app.command("remove")
def track_remove(
    app_id: int = typer.Option(..., "--app-id"),
    keyword: str = typer.Option(..., "--keyword"),
    country: str = typer.Option(..., "--country"),
    device: str = typer.Option("iphone", "--device"),
) -> None:
    require_initialized()
    with session_scope() as session:
        matches = list_targets(
            session, apple_id=app_id, keyword=keyword, country=country, device=device
        )
        if not matches:
            raise typer.BadParameter("tracking target not found")
        matches[0].active = False
        emit("Tracking target deactivated; its rank history was preserved.")


@track_app.command("list")
def track_list() -> None:
    require_initialized()
    with session_scope() as session:
        targets = list_targets(session)
        table = Table(
            "ID", "App", "Keyword", "Country", "Device", "Status", title="Tracking targets"
        )
        for item in targets:
            table.add_row(
                str(item.id),
                item.app.name,
                item.keyword.keyword,
                item.storefront.country_code,
                item.device,
                "active" if item.active else "inactive",
            )
        print_table(table)


@track_app.command("seed")
def track_seed(app_id: int = typer.Option(6771773264, "--app-id")) -> None:
    require_initialized()
    with session_scope() as session:
        created = seed_targets(session, app_id)
        emit(f"Created {created} new target(s); duplicates were ignored.")


@app.command("check")
def check(
    app_id: int | None = typer.Option(None, "--app-id"),
    country: str | None = typer.Option(None, "--country"),
    keyword: str | None = typer.Option(None, "--keyword"),
    device: str | None = typer.Option(None, "--device"),
    only_missing_today: bool = typer.Option(False, "--only-missing-today"),
    concurrency: int | None = typer.Option(None, "--concurrency", min=1, max=10),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run Apple searches for matching active targets."""

    require_initialized()
    settings = load_settings()
    with session_scope() as session:
        targets = list_targets(
            session,
            apple_id=app_id,
            country=country,
            keyword=keyword,
            device=device,
            active_only=True,
        )
        if only_missing_today:
            targets = filter_missing_today(session, targets)
        if not targets:
            emit("No matching active tracking targets need checking.", style="yellow")
            return
        unique = {
            (target.keyword.normalized_keyword, target.storefront.country_code, target.device)
            for target in targets
        }
        if dry_run:
            emit(f"Dry run: {len(targets)} target(s), {len(unique)} Apple request(s).")
            for target in targets:
                emit(
                    f"  {target.app.name} · {target.keyword.keyword} · "
                    f"{target.storefront.country_code} · {target.device}"
                )
            return
        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"), console=console, disable=quiet_mode
        ) as progress:
            task = progress.add_task(f"Checking {len(targets)} targets…", total=len(targets))
            result = run_checks(
                session,
                targets,
                settings,
                concurrency=concurrency,
                progress=lambda amount: progress.advance(task, amount),
            )
        target_map = {target.id: target for target in targets}
        table = Table(
            "App", "Keyword", "Country", "Device", "Rank", "Status", title="Check results"
        )
        for row in result.checks:
            target = target_map[row.tracking_target_id]
            table.add_row(
                target.app.name,
                target.keyword.keyword,
                target.storefront.country_code,
                target.device,
                _rank(row),
                row.status,
            )
        print_table(table)
        emit(
            f"Stored {len(result.checks)} checks from {result.searches} unique Apple searches; "
            f"{result.failures} search failure(s)."
        )
        if result.searches and result.failures == result.searches:
            raise typer.Exit(1)


def _rank(check: RankCheck) -> str:
    return f"#{check.rank}" if check.found and check.rank is not None else f">{check.result_limit}"


def _ranking_rows(session: Session, targets: list[TrackingTarget]) -> list[RankingRow]:
    pairs = latest_pairs(session, targets)
    return [
        RankingRow(target, pair[0], pair[1]) for target in targets if (pair := pairs.get(target.id))
    ]


@app.command("rankings")
def rankings(
    app_id: int | None = typer.Option(None, "--app-id"),
    country: str | None = typer.Option(None, "--country"),
    keyword: str | None = typer.Option(None, "--keyword"),
    device: str | None = typer.Option(None, "--device"),
    limit: int = typer.Option(100, "--limit", min=1),
    found_only: bool = typer.Option(False, "--found-only"),
) -> None:
    require_initialized()
    with session_scope() as session:
        rows = _ranking_rows(
            session,
            list_targets(
                session,
                apple_id=app_id,
                country=country,
                keyword=keyword,
                device=device,
            ),
        )
        if found_only:
            rows = [row for row in rows if row.latest.found]
        rows = sorted(rows, key=lambda row: (row.latest.rank is None, row.latest.rank or 10**9))[
            :limit
        ]
        table = Table(
            "App",
            "Keyword",
            "Country",
            "Device",
            "Rank",
            "Volume est.",
            "Difficulty est.",
            "Previous",
            "Change",
            "Checked at",
            title="Latest rankings",
        )
        for row in rows:
            style = (
                "green"
                if row.change.startswith("+") or row.change == "NEW"
                else "red"
                if row.change.startswith("-") or row.change == "LOST"
                else None
            )
            table.add_row(
                row.target.app.name,
                row.target.keyword.keyword,
                row.target.storefront.country_code,
                row.target.device,
                _rank(row.latest),
                str(row.latest.estimate.volume)
                if row.latest.estimate and row.latest.estimate.volume is not None
                else "—",
                str(row.latest.estimate.difficulty)
                if row.latest.estimate and row.latest.estimate.difficulty is not None
                else "—",
                _rank(row.previous) if row.previous else "—",
                f"[{style}]{row.change}[/]" if style else row.change,
                local_timestamp(row.latest.checked_at),
            )
        print_table(table)


@app.command("history")
def history(
    keyword: str = typer.Option(..., "--keyword"),
    country: str = typer.Option(..., "--country"),
    app_id: int | None = typer.Option(None, "--app-id"),
    device: str | None = typer.Option(None, "--device"),
    days: int = typer.Option(30, "--days", min=1),
    from_date: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    to_date: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    chart: bool = typer.Option(False, "--chart"),
) -> None:
    require_initialized()
    try:
        parsed_from = date.fromisoformat(from_date) if from_date else None
        parsed_to = date.fromisoformat(to_date) if to_date else None
    except ValueError as exc:
        raise typer.BadParameter("dates must use YYYY-MM-DD") from exc
    start = (
        parse_date_start(parsed_from) if parsed_from else datetime.now(UTC) - timedelta(days=days)
    )
    end = datetime.combine(parsed_to, time.max, tzinfo=UTC) if parsed_to else None
    with session_scope() as session:
        targets = list_targets(
            session, apple_id=app_id, country=country, keyword=keyword, device=device
        )
        checks = successful_checks(session, targets, start=start, end=end)
        target_map = {target.id: target for target in targets}
        if chart and len(checks) >= 2:
            _print_history_chart(checks, target_map)
        table = Table(
            "App", "Keyword", "Country", "Device", "Rank", "Checked at", title="Rank history"
        )
        for row in checks:
            target = target_map[row.tracking_target_id]
            table.add_row(
                target.app.name,
                target.keyword.keyword,
                target.storefront.country_code,
                target.device,
                _rank(row),
                local_timestamp(row.checked_at),
            )
        print_table(table)


def _print_history_chart(checks: list[RankCheck], target_map: dict[int, TrackingTarget]) -> None:
    blocks = "▁▂▃▄▅▆▇█"
    for target_id in sorted({check.tracking_target_id for check in checks}):
        series = [check for check in checks if check.tracking_target_id == target_id]
        ranks = [check.rank for check in series if check.rank is not None]
        if len(ranks) < 2:
            continue
        worst, best = max(ranks), min(ranks)
        span = max(worst - best, 1)
        spark = "".join(
            blocks[round((worst - rank) / span * 7)] if rank is not None else "·"
            for rank in [check.rank for check in series]
        )
        target = target_map[target_id]
        emit(
            f"{target.app.name} · {target.keyword.keyword} · "
            f"{target.storefront.country_code} · {target.device}: {spark}  Better ↑"
        )


@app.command("summary")
def summary(
    app_id: int | None = typer.Option(None, "--app-id"),
    country: str | None = typer.Option(None, "--country"),
    device: str | None = typer.Option(None, "--device"),
    days: int = typer.Option(7, "--days", min=1),
) -> None:
    require_initialized()
    with session_scope() as session:
        targets = list_targets(session, apple_id=app_id, country=country, device=device)
        rows = _ranking_rows_with_period(session, targets, days)
        value = calculate_summary(rows)
        table = Table("Metric", "Value", title=f"ASO summary · last {days} days")
        for label, item in [
            ("Tracked keywords", value.tracked_keywords),
            ("Top 10", value.top_10),
            ("Top 20", value.top_20),
            ("Top 50", value.top_50),
            ("Top 100", value.top_100),
            ("Absent from retrieved results", value.absent),
            ("Best ranking keyword", value.best_keyword),
            ("Biggest positive mover", value.biggest_positive),
            ("Biggest negative mover", value.biggest_negative),
            ("Newly ranked", value.newly_ranked),
            ("Lost", value.lost),
            (
                "Average rank among found",
                f"{value.average_rank:.1f}" if value.average_rank is not None else "—",
            ),
        ]:
            table.add_row(label, str(item))
        print_table(table)


def _ranking_rows_with_period(
    session: Session, targets: list[TrackingTarget], days: int
) -> list[RankingRow]:
    checks = successful_checks(session, targets, start=datetime.now(UTC) - timedelta(days=days))
    grouped: dict[int, list[RankCheck]] = {}
    for check_item in checks:
        grouped.setdefault(check_item.tracking_target_id, []).append(check_item)
    return [
        RankingRow(target, items[-1], items[-2] if len(items) > 1 else None)
        for target in targets
        if (items := grouped.get(target.id))
    ]


@app.command("opportunities")
def opportunities(
    app_id: int | None = typer.Option(None, "--app-id"),
    country: str | None = typer.Option(None, "--country"),
    device: str | None = typer.Option(None, "--device"),
) -> None:
    require_initialized()
    with session_scope() as session:
        rows = _ranking_rows(
            session, list_targets(session, apple_id=app_id, country=country, device=device)
        )
        table = Table(
            "Group",
            "App",
            "Keyword",
            "Country",
            "Device",
            "Rank",
            title="Ranking opportunities (no search-volume estimates)",
        )
        for row in sorted(
            rows, key=lambda item: (item.latest.rank is None, item.latest.rank or 999)
        ):
            table.add_row(
                opportunity_group(row.latest),
                row.target.app.name,
                row.target.keyword.keyword,
                row.target.storefront.country_code,
                row.target.device,
                _rank(row.latest),
            )
        print_table(table)


def _all_targets(session: Session) -> list[TrackingTarget]:
    return list_targets(session)


@export_app.command("csv")
def export_csv(output: Path = typer.Option(..., "--output")) -> None:
    require_initialized()
    with session_scope() as session:
        count = export_latest_csv(session, _all_targets(session), output)
    emit(f"Exported {count} latest ranking row(s) to {output.resolve()}")


@export_app.command("history")
def export_history(output: Path = typer.Option(..., "--output")) -> None:
    require_initialized()
    with session_scope() as session:
        count = export_history_csv(session, _all_targets(session), output)
    emit(f"Exported {count} history row(s) to {output.resolve()}")


@export_app.command("json")
def export_json_command(output: Path = typer.Option(..., "--output")) -> None:
    require_initialized()
    with session_scope() as session:
        count = export_json(session, _all_targets(session), output)
    emit(f"Exported local data ({count} history rows) to {output.resolve()}")


@app.command("report")
def report(
    output: Path = typer.Option(Path("reports/aso-report.html"), "--output"),
    open_report: bool = typer.Option(
        False, "--open", help="Open the generated local file in a browser."
    ),
) -> None:
    require_initialized()
    with session_scope() as session:
        count = generate_html_report(session, _all_targets(session), output)
    resolved = output.resolve()
    emit(f"Generated standalone report with {count} latest row(s): {resolved}")
    if open_report:
        webbrowser.open(resolved.as_uri())


@app.command("dashboard")
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host", help="Local interface to bind."),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    mcp_enabled: bool = typer.Option(
        True,
        "--mcp/--no-mcp",
        help="Start the local MCP read/write action endpoint with the dashboard.",
    ),
    mcp_port: int = typer.Option(8766, "--mcp-port", min=1, max=65535),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Launch the interactive local-only web dashboard."""

    run_migrations()
    write_default_config()
    with session_scope() as session:
        if session.scalar(select(Storefront.id).limit(1)) is None:
            for code, name in INITIAL_COUNTRIES.items():
                add_storefront(session, code, name)
    if host not in {"127.0.0.1", "localhost", "::1"}:
        emit(
            "Warning: binding beyond loopback exposes the dashboard to your local network.",
            style="yellow",
        )
    if mcp_enabled and mcp_port == port:
        if port >= 65535:
            raise typer.BadParameter("cannot select an MCP port when --port is 65535")
        mcp_port = port + 1
    from local_aso_tracker.web.server import serve_dashboard

    serve_dashboard(
        host=host,
        port=port,
        mcp_enabled=mcp_enabled,
        mcp_port=mcp_port,
        open_browser=open_browser,
    )


def main() -> None:
    """Console-script wrapper with clean ordinary error handling."""

    try:
        app()
    except (ValueError, ValidationError, SQLAlchemyError) as exc:
        logging.getLogger(__name__).debug("Command failed", exc_info=True)
        error_console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
