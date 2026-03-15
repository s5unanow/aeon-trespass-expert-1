"""CLI command: atr qa — run QA checks on existing artifacts."""

from __future__ import annotations

import json

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import RenderPageV1


def qa(
    doc: str = typer.Option(..., "--doc", help="Document id"),
) -> None:
    """Run QA checks on existing artifacts for a document."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)

    # Find artifacts
    en_ir_dir = store.root / doc / "page_ir.v1.en" / "page" / "p0001"
    ru_ir_dir = store.root / doc / "page_ir.v1.ru" / "page" / "p0001"
    render_dir = store.root / doc / "render_page.v1" / "page" / "p0001"

    errors: list[str] = []

    for d, label in [(en_ir_dir, "EN IR"), (ru_ir_dir, "RU IR"), (render_dir, "Render")]:
        if not d.exists():
            errors.append(f"Missing {label} artifacts: {d}")

    if errors:
        for e in errors:
            typer.echo(f"  ERROR: {e}", err=True)
        raise typer.Exit(1)

    # Load latest artifacts
    en_file = next(en_ir_dir.glob("*.json"))
    ru_file = next(ru_ir_dir.glob("*.json"))
    render_file = next(render_dir.glob("*.json"))

    en_ir = PageIRV1.model_validate(json.loads(en_file.read_text()))
    ru_ir = PageIRV1.model_validate(json.loads(ru_file.read_text()))
    render = RenderPageV1.model_validate(json.loads(render_file.read_text()))

    # Run QA rules
    records = evaluate_icon_count(en_ir, ru_ir, render)

    if records:
        for r in records:
            typer.echo(f"  {r.severity.value}: [{r.code}] {r.message}")
        typer.echo(f"\n{len(records)} QA issue(s) found.")
        raise typer.Exit(1)
    else:
        typer.echo("QA passed: all checks clean.")
