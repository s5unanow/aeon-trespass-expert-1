"""CLI commands: atr runs list / atr runs show — query run history."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import typer

from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run, list_all_runs, list_runs


def runs_list(
    doc: str = typer.Option("", "--doc", help="Filter by document id"),
    limit: int = typer.Option(20, "--limit", help="Max runs to show"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List recent pipeline runs."""
    conn = _open_conn()
    try:
        rows = list_runs(conn, doc) if doc else list_all_runs(conn)
        rows = rows[:limit]

        if output_json:
            data = [_run_row_to_dict(r) for r in rows]
            typer.echo(json.dumps(data, indent=2))
            return

        if not rows:
            typer.echo("No runs found.")
            return

        # Tabular output
        typer.echo(f"{'RUN ID':<20} {'DOCUMENT':<25} {'STATUS':<12} {'STARTED':<26}")
        typer.echo("-" * 83)
        for r in rows:
            typer.echo(
                f"{r['run_id']:<20} {r['document_id']:<25} {r['status']:<12} {r['started_at']:<26}"
            )
    finally:
        conn.close()


def runs_show(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show detailed info for a specific run, including per-stage timing."""
    conn = _open_conn()
    try:
        run = get_run(conn, run_id)
        if run is None:
            typer.echo(f"Run not found: {run_id}", err=True)
            raise typer.Exit(1)

        events = list_stage_events(conn, run_id=run_id)

        if output_json:
            data = _run_row_to_dict(run)
            data["stages"] = [_event_to_dict(ev) for ev in events]
            typer.echo(json.dumps(data, indent=2))
            return

        typer.echo(f"Run:      {run['run_id']}")
        typer.echo(f"Document: {run['document_id']}")
        typer.echo(f"Status:   {run['status']}")
        typer.echo(f"Edition:  {run['edition'] or 'all'}")
        typer.echo(f"Version:  {run['pipeline_version']}")
        typer.echo(f"Started:  {run['started_at']}")
        typer.echo(f"Finished: {run['finished_at'] or '-'}")
        typer.echo(f"Git:      {run['git_commit'] or '-'}")
        typer.echo(f"Config:   {run['config_hash']}")

        if events:
            typer.echo(f"\n{'STAGE':<20} {'SCOPE':<10} {'STATUS':<12} {'DURATION':<10}")
            typer.echo("-" * 52)
            for ev in events:
                dur = f"{ev['duration_ms']}ms" if ev["duration_ms"] else "-"
                typer.echo(f"{ev['stage_name']:<20} {ev['scope']:<10} {ev['status']:<12} {dur:<10}")
    finally:
        conn.close()


def _open_conn() -> sqlite3.Connection:
    """Open registry DB from standard location."""
    repo_root = _find_repo_root()
    return open_registry(repo_root / "var" / "registry.db")


def _find_repo_root() -> Path:
    """Walk up from cwd to find repo root (has configs/ and .git)."""
    current = Path.cwd()
    for p in [current, *current.parents]:
        if (p / "configs").is_dir() and (p / ".git").exists():
            return p
    return current


def _run_row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {k: row[k] for k in row.keys()}  # noqa: SIM118


def _event_to_dict(ev: sqlite3.Row) -> dict[str, object]:
    return {k: ev[k] for k in ev.keys()}  # noqa: SIM118
