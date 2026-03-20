"""CLI command: atr verify-refs — run cross-stage reference-integrity checks."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.cross_stage_runner import run_cross_stage_verification
from atr_pipeline.eval.invariant_models import VerificationReport
from atr_pipeline.store.artifact_store import ArtifactStore


def verify_refs_command(
    doc: str = typer.Option(..., "--doc", help="Document id to verify"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
) -> None:
    """Run cross-stage reference-integrity checks on pipeline artifacts."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    page_filter = _parse_pages(pages) if pages else None

    report = run_cross_stage_verification(
        document_id=doc,
        store=store,
        page_filter=page_filter,
    )

    _print_summary(report)

    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
            f.write("\n")
        typer.echo(f"Report written: {output_path}")

    if report.blocking:
        raise typer.Exit(1)


def _parse_pages(pages_str: str) -> list[str]:
    """Parse comma-separated page IDs."""
    return [p.strip() for p in pages_str.split(",") if p.strip()]


def _print_summary(report: VerificationReport) -> None:
    """Print a human-readable cross-stage verification summary."""
    typer.echo(f"\nCross-stage refs: {report.document_id}")
    typer.echo(f"Timestamp:        {report.timestamp}")
    typer.echo(f"Pages:            {len(report.pages)}")

    total_records = sum(len(p.records) for p in report.pages)
    typer.echo(f"Findings:         {total_records}")

    if report.severity_counts:
        counts_str = ", ".join(f"{k}={v}" for k, v in sorted(report.severity_counts.items()))
        typer.echo(f"Severity:         {counts_str}")

    if total_records:
        typer.echo(f"\n{'PAGE':<10} {'CODE':<25} {'SEV':<10} {'ENTITY':<25}")
        typer.echo("-" * 70)
        for page_result in report.pages:
            for r in page_result.records:
                typer.echo(
                    f"{r.page_id or '':<10} {r.code:<25} {r.severity:<10} {r.entity_ref or '':<25}"
                )

    status = "PASSED" if report.passed else "FAILED"
    typer.echo(f"\nResult: {status}")
