"""CLI command: atr bench — run a checkpointed extraction benchmark ladder."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.bench_models import BenchmarkReport
from atr_pipeline.eval.bench_report import print_bench_summary, write_bench_report_json
from atr_pipeline.eval.bench_runner import run_benchmark_ladder
from atr_pipeline.store.artifact_store import ArtifactStore


def _default_store_factory(document_id: str) -> ArtifactStore:
    """Create an artifact store for a document using its config."""
    config = load_document_config(document_id)
    return ArtifactStore(config.artifact_root)


def bench_command(
    ladder: str = "extraction_ladder",
    output_json: str = "",
    baseline: str = "",
    fail_on_regression: bool = False,
) -> None:
    """Run a checkpointed extraction benchmark ladder."""
    baseline_report: BenchmarkReport | None = None
    if baseline:
        baseline_path = Path(baseline)
        if not baseline_path.exists():
            typer.echo(f"Baseline report not found: {baseline_path}", err=True)
            raise typer.Exit(1)
        baseline_report = BenchmarkReport.model_validate_json(baseline_path.read_text())

    report = run_benchmark_ladder(
        ladder_name=ladder,
        store_factory=_default_store_factory,
        baseline=baseline_report,
    )

    print_bench_summary(report)

    if output_json:
        write_bench_report_json(report, Path(output_json))

    if fail_on_regression and report.regressions:
        typer.echo(
            f"\nFailing due to {len(report.regressions)} backward regression(s).",
            err=True,
        )
        raise typer.Exit(1)

    if not report.passed:
        raise typer.Exit(1)
