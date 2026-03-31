"""Benchmark ladder report: terminal summary and JSON export."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.eval.bench_models import BenchmarkReport


def print_bench_summary(report: BenchmarkReport) -> None:
    """Print a human-readable table of benchmark results."""
    typer.echo(f"\nBenchmark: {report.ladder_name}")
    typer.echo("─" * 60)
    typer.echo(f"  {'#':>2}  {'CHECKPOINT':<25} {'GOLDEN SET':<20} {'STATUS':>6}")
    typer.echo("─" * 60)

    for c in report.checkpoints:
        if c.skipped:
            status = "SKIP"
        elif c.passed:
            status = "PASS"
        else:
            status = "FAIL"

        marker = ""
        if c.is_frontier:
            marker = "  \u2190 frontier"
        elif c.is_regression:
            marker = "  \u2190 regression"

        typer.echo(f"  {c.order:>2}  {c.name:<25} {c.golden_set:<20} {status:>6}{marker}")

    typer.echo("─" * 60)

    if report.frontier_checkpoint is not None:
        frontier_name = next(
            (c.name for c in report.checkpoints if c.order == report.frontier_checkpoint), "?"
        )
        typer.echo(f"Frontier: #{report.frontier_checkpoint} ({frontier_name})")
    else:
        typer.echo("Frontier: none (all passed)")

    typer.echo(f"Highest passing streak: #{report.highest_passing}")

    if report.regressions:
        names = ", ".join(f"#{o}" for o in report.regressions)
        typer.echo(f"Backward regressions: {names}")
    else:
        typer.echo("Backward regressions: none")

    status = "PASSED" if report.passed else "FAILED"
    typer.echo(f"\nResult: {status}")


def write_bench_report_json(report: BenchmarkReport, output_path: Path) -> None:
    """Write the benchmark report as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))
        f.write("\n")
    typer.echo(f"Benchmark report written: {output_path}")
