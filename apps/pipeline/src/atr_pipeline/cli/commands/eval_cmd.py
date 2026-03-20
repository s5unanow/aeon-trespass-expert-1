"""CLI command: atr eval — run extraction evaluation against golden sets."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.config_loader import discover_golden_sets, load_golden_set
from atr_pipeline.eval.models import EvalReport
from atr_pipeline.eval.report import print_summary, write_report_json
from atr_pipeline.eval.runner import load_page_ir, run_evaluation
from atr_pipeline.eval.thresholds import ThresholdConfig, load_thresholds
from atr_pipeline.store.artifact_store import ArtifactStore


def eval_command(
    golden_set: str = typer.Option(..., "--golden-set", help="Golden set name or 'all'"),
    doc: str = typer.Option("", "--doc", help="Document id (inferred from golden set if omitted)"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
    overlays: bool = typer.Option(False, "--overlays", help="Generate visual overlay PNGs"),
    fail_on_threshold: bool = typer.Option(
        False, "--fail-on-threshold", help="Fail if blocking thresholds are not met"
    ),
) -> None:
    """Run extraction evaluation against a golden set."""
    if golden_set == "all":
        _run_all_golden_sets(output_json=output_json, fail_on_threshold=fail_on_threshold)
        return

    gs_config = load_golden_set(golden_set)
    document_id = doc or gs_config.document_id
    config = load_document_config(document_id)
    store = ArtifactStore(config.artifact_root)
    repo_root = config.repo_root
    page_filter = _parse_pages(pages) if pages else None
    threshold_config = _load_threshold_config(repo_root) if fail_on_threshold else None

    report = run_evaluation(
        golden_set_name=golden_set,
        document_id=document_id,
        store=store,
        repo_root=repo_root,
        page_filter=page_filter,
        threshold_config=threshold_config,
    )

    print_summary(report)

    if output_json:
        write_report_json(report, Path(output_json))

    if overlays:
        _generate_overlays(store, document_id, report)

    if not report.passed:
        raise typer.Exit(1)


def _run_all_golden_sets(*, output_json: str, fail_on_threshold: bool) -> None:
    """Discover and run all golden sets, fail if any fail."""
    names = discover_golden_sets()
    if not names:
        typer.echo("No golden sets found.", err=True)
        raise typer.Exit(1)

    typer.echo(f"Running {len(names)} golden set(s): {', '.join(names)}")
    all_reports: list[EvalReport] = []
    any_failed = False
    threshold_config: ThresholdConfig | None = None

    for name in names:
        gs_config = load_golden_set(name)
        document_id = gs_config.document_id
        try:
            config = load_document_config(document_id)
        except FileNotFoundError:
            typer.echo(f"  SKIP {name}: document config not found for {document_id}", err=True)
            continue

        if fail_on_threshold and threshold_config is None:
            threshold_config = _load_threshold_config(config.repo_root)

        store = ArtifactStore(config.artifact_root)
        report = run_evaluation(
            golden_set_name=name,
            document_id=document_id,
            store=store,
            repo_root=config.repo_root,
            threshold_config=threshold_config,
        )
        all_reports.append(report)
        status = "PASS" if report.passed else "FAIL"
        typer.echo(f"  {status} {name} ({document_id})")
        if not report.passed:
            any_failed = True
            print_summary(report)

    if output_json and all_reports:
        combined = [r.model_dump(mode="json") for r in all_reports]
        Path(output_json).write_text(json.dumps(combined, indent=2))

    if any_failed:
        raise typer.Exit(1)


def _load_threshold_config(repo_root: Path) -> ThresholdConfig | None:
    """Load threshold config, returning None if not found."""
    try:
        return load_thresholds(repo_root=repo_root)
    except FileNotFoundError:
        typer.echo("Warning: threshold config not found, skipping threshold checks", err=True)
        return None


def _parse_pages(pages_str: str) -> list[str]:
    """Parse comma-separated page IDs."""
    return [p.strip() for p in pages_str.split(",") if p.strip()]


def _generate_overlays(
    store: ArtifactStore,
    document_id: str,
    report: EvalReport,
) -> None:
    """Generate overlay PNGs for evaluated pages."""
    from atr_pipeline.eval.overlay import draw_ir_overlay

    for page_result in report.pages:
        page_id = page_result.page_id
        raster_dir = store.root / document_id / "raster" / "page" / page_id
        if not raster_dir.exists():
            typer.echo(f"  SKIP overlay {page_id}: no raster", err=True)
            continue

        rasters = sorted(raster_dir.glob("*.png"))
        if not rasters:
            continue

        raster_path = rasters[-1]
        page_ir = load_page_ir(store, document_id, page_id)
        if page_ir is None:
            continue

        png_bytes = draw_ir_overlay(raster_path, page_ir)
        out_dir = store.root / document_id / "eval_overlay" / "ir" / page_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "overlay.png"
        out_path.write_bytes(png_bytes)
        typer.echo(f"  Overlay: {out_path}")
