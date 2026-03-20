"""Evaluation report output: terminal summary and JSON export."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.eval.models import EvalReport


def print_summary(report: EvalReport) -> None:
    """Print a human-readable summary of the evaluation report."""
    typer.echo(f"\nEvaluation: {report.golden_set_name} / {report.document_id}")
    typer.echo(f"Timestamp:  {report.timestamp}")
    typer.echo(f"Pages:      {len(report.pages)}")
    typer.echo("")

    typer.echo(f"{'PAGE':<10} {'METRIC':<25} {'VALUE':>8} {'EXPECTED':>10} {'PASS':>6}")
    typer.echo("-" * 61)

    for page_result in report.pages:
        for m in page_result.metrics:
            exp_str = f"{m.expected:.2f}" if m.expected is not None else "—"
            status = "OK" if m.passed else "FAIL"
            typer.echo(
                f"{m.page_id:<10} {m.metric_name:<25} {m.value:>8.2f} {exp_str:>10} {status:>6}"
            )

    typer.echo("-" * 61)
    if report.aggregate:
        typer.echo("Aggregate:")
        for key, val in sorted(report.aggregate.items()):
            typer.echo(f"  {key}: {val:.4f}")

    if report.threshold_results:
        typer.echo("")
        typer.echo(f"{'THRESHOLD':<45} {'VALUE':>8} {'MIN':>8} {'BLOCK':>6} {'PASS':>6}")
        typer.echo("-" * 75)
        for t in report.threshold_results:
            val_str = f"{t.value:.4f}" if t.value is not None else "N/A"
            block_str = "YES" if t.blocking else "no"
            status = "OK" if t.passed else "FAIL"
            typer.echo(
                f"{t.name:<45} {val_str:>8} {t.threshold_min:>8.4f} {block_str:>6} {status:>6}"
            )
        typer.echo("-" * 75)

    status = "PASSED" if report.passed else "FAILED"
    typer.echo(f"\nResult: {status}")


def write_report_json(report: EvalReport, output_path: Path) -> None:
    """Write the evaluation report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
        f.write("\n")
    typer.echo(f"Report written: {output_path}")
