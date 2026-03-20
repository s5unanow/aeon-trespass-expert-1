"""CLI command: atr eval — run extraction evaluation against golden sets."""

from __future__ import annotations

from pathlib import Path

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.eval.models import EvalReport
from atr_pipeline.eval.report import print_summary, write_report_json
from atr_pipeline.eval.runner import run_evaluation
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1


def eval_command(
    golden_set: str = typer.Option(..., "--golden-set", help="Golden set name (e.g. 'core')"),
    doc: str = typer.Option(..., "--doc", help="Document id to evaluate"),
    pages: str = typer.Option("", "--pages", help="Page filter: 'p0001' or 'p0001,p0002'"),
    output_json: str = typer.Option("", "--output-json", help="Path to write JSON report"),
    overlays: bool = typer.Option(False, "--overlays", help="Generate visual overlay PNGs"),
) -> None:
    """Run extraction evaluation against a golden set."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)
    repo_root = config.repo_root

    page_filter = _parse_pages(pages) if pages else None

    report = run_evaluation(
        golden_set_name=golden_set,
        document_id=doc,
        store=store,
        repo_root=repo_root,
        page_filter=page_filter,
    )

    print_summary(report)

    if output_json:
        write_report_json(report, Path(output_json))

    if overlays:
        _generate_overlays(store, doc, report, repo_root)

    if not report.passed:
        raise typer.Exit(1)


def _parse_pages(pages_str: str) -> list[str]:
    """Parse comma-separated page IDs."""
    return [p.strip() for p in pages_str.split(",") if p.strip()]


def _generate_overlays(
    store: ArtifactStore,
    document_id: str,
    report: EvalReport,
    repo_root: Path,
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
        page_ir = _load_ir_for_overlay(store, document_id, page_id)
        if page_ir is None:
            continue

        png_bytes = draw_ir_overlay(raster_path, page_ir)
        out_dir = store.root / document_id / "eval_overlay" / "ir" / page_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "overlay.png"
        out_path.write_bytes(png_bytes)
        typer.echo(f"  Overlay: {out_path}")


def _load_ir_for_overlay(
    store: ArtifactStore,
    document_id: str,
    page_id: str,
) -> PageIRV1 | None:
    """Load page IR for overlay generation."""
    import json

    page_dir = store.root / document_id / "page_ir.v1.en" / "page" / page_id
    if not page_dir.exists():
        return None
    jsons = sorted(page_dir.glob("*.json"))
    if not jsons:
        return None
    return PageIRV1.model_validate(json.loads(jsons[-1].read_text()))
