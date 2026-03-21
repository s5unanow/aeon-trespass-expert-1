"""Audit report output: terminal summary and JSON export."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.eval.audit_models import AuditReport


def print_audit_summary(report: AuditReport) -> None:
    """Print a human-readable summary of the audit report."""
    typer.echo(f"\nAudit: {report.document_id}")
    typer.echo(f"Timestamp:       {report.timestamp}")
    typer.echo(f"Pages (scope):   {report.pages_in_scope}")
    typer.echo(f"Pages (audited): {report.pages_audited}")
    typer.echo(f"Pages (missing): {report.pages_missing_ir}")
    typer.echo("")

    # Issue summary
    if report.total_issue_counts:
        typer.echo("Issue counts by category:")
        for code, count in sorted(report.total_issue_counts.items()):
            typer.echo(f"  {code:<35} {count:>5}")
        typer.echo("")

    # Hard / fallback pages
    if report.hard_pages:
        typer.echo(f"Hard pages ({len(report.hard_pages)}): {', '.join(report.hard_pages)}")
    if report.fallback_route_pages:
        typer.echo(
            f"Fallback-route pages ({len(report.fallback_route_pages)}): "
            f"{', '.join(report.fallback_route_pages)}"
        )
    if report.invariant_failure_pages:
        typer.echo(
            f"Invariant-failure pages ({len(report.invariant_failure_pages)}): "
            f"{', '.join(report.invariant_failure_pages)}"
        )
    if report.reading_order_failure_pages:
        typer.echo(
            f"Reading-order failures ({len(report.reading_order_failure_pages)}): "
            f"{', '.join(report.reading_order_failure_pages)}"
        )

    # Baseline delta
    if report.baseline_delta is not None:
        typer.echo("")
        typer.echo(f"Baseline snapshot: {report.baseline_snapshot_id}")
        typer.echo(f"{'CATEGORY':<35} {'DELTA':>8}")
        typer.echo("-" * 45)
        for code, delta in sorted(report.baseline_delta.items()):
            sign = "+" if delta > 0 else ""
            typer.echo(f"{code:<35} {sign}{delta:>7.0f}")

    typer.echo("\nResult: DIAGNOSTIC (non-blocking)")


def write_audit_json(report: AuditReport, output_path: Path) -> None:
    """Write the audit report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
        f.write("\n")
    typer.echo(f"Audit report written: {output_path}")
