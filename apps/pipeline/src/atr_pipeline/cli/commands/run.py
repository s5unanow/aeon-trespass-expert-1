"""CLI command: atr run — execute a pipeline stage range for a document."""

from __future__ import annotations

import uuid

import typer

from atr_pipeline.config import load_document_config
from atr_pipeline.registry.db import open_registry
from atr_pipeline.registry.runs import finish_run, start_run
from atr_pipeline.runner.plan import resolve_stage_range
from atr_pipeline.store.artifact_store import ArtifactStore


def run(
    doc: str = typer.Option(..., "--doc", help="Document id"),
    from_stage: str = typer.Option("ingest", "--from", help="First stage to run"),
    to_stage: str = typer.Option("qa", "--to", help="Last stage to run"),
) -> None:
    """Run a range of pipeline stages for a document."""
    config = load_document_config(doc)
    store = ArtifactStore(config.artifact_root)
    conn = open_registry(config.repo_root / "var" / "registry.db")

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    start_run(
        conn,
        run_id=run_id,
        document_id=doc,
        pipeline_version=config.pipeline.version,
        config_hash="",
    )

    stages = resolve_stage_range(from_stage=from_stage, to_stage=to_stage)
    typer.echo(f"Running stages: {' → '.join(stages)}")

    # Import stage implementations lazily
    from atr_pipeline.services.llm.mock_translator import MockTranslator
    from atr_pipeline.services.pdf.rasterizer import render_page_png
    from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
    from atr_pipeline.stages.ingest.manifest_builder import build_manifest
    from atr_pipeline.stages.ingest.pdf_fingerprint import fingerprint_pdf
    from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
    from atr_pipeline.stages.render.page_builder import build_render_page
    from atr_pipeline.stages.structure.block_builder import build_page_ir_simple
    from atr_pipeline.stages.symbols.catalog_loader import load_symbol_catalog
    from atr_pipeline.stages.symbols.matcher import match_symbols
    from atr_pipeline.stages.translation.planner import build_translation_batch
    from atr_pipeline.stages.translation.validator import validate_translation
    from atr_schemas.enums import LanguageCode
    from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, ParagraphBlock

    # State accumulated through stages
    manifest = None
    native_page = None
    symbol_matches = None
    en_ir = None
    ru_ir = None
    render_page = None
    has_errors = False

    for stage_name in stages:
        typer.echo(f"  [{stage_name}]")
        try:
            if stage_name == "ingest":
                sha256, page_count = fingerprint_pdf(config.source_pdf_path)
                manifest = build_manifest(
                    document_id=doc, source_pdf_sha256=sha256, page_count=page_count,
                )
                dpi = config.extraction.layout.dpi
                for pnum in range(1, page_count + 1):
                    pid = f"p{pnum:04d}"
                    png_bytes = render_page_png(config.source_pdf_path, pnum, dpi=dpi)
                    store.put_bytes(
                        document_id=doc, schema_family="raster", scope="page",
                        entity_id=pid, data=png_bytes, extension=".png",
                    )
                store.put_json(
                    document_id=doc, schema_family="source_manifest",
                    scope="document", entity_id=doc, data=manifest,
                )

            elif stage_name == "extract_native":
                native_page = extract_native_page(
                    config.source_pdf_path, page_number=1, document_id=doc,
                )
                store.put_json(
                    document_id=doc, schema_family="native_page.v1",
                    scope="page", entity_id="p0001", data=native_page,
                )

            elif stage_name == "symbols":
                assert native_page is not None
                raster_dir = store.root / doc / "raster" / "page" / "p0001"
                raster_files = list(raster_dir.glob("*.png"))
                assert raster_files, "No raster found for p0001"
                catalog = load_symbol_catalog(config.symbol_catalog_path)  # type: ignore[arg-type]
                symbol_matches = match_symbols(
                    native_page, raster_files[0], catalog, repo_root=config.repo_root,
                )
                store.put_json(
                    document_id=doc, schema_family="symbol_match_set.v1",
                    scope="page", entity_id="p0001", data=symbol_matches,
                )

            elif stage_name == "structure":
                assert native_page is not None and symbol_matches is not None
                en_ir = build_page_ir_simple(native_page, symbol_matches)
                store.put_json(
                    document_id=doc, schema_family="page_ir.v1.en",
                    scope="page", entity_id="p0001", data=en_ir,
                )

            elif stage_name == "translate":
                assert en_ir is not None
                batch = build_translation_batch(en_ir)
                translator = MockTranslator()
                result = translator.translate_batch(batch)
                errors = validate_translation(batch, result)
                if errors:
                    for e in errors:
                        typer.echo(f"    WARN: {e}", err=True)

                # Build Russian IR
                ru_blocks = []
                for seg in result.segments:
                    src_block = next(b for b in en_ir.blocks if b.block_id == seg.segment_id)
                    if src_block.type == "heading":
                        ru_blocks.append(
                            HeadingBlock(
                                block_id=seg.segment_id, level=2,
                                children=list(seg.target_inline),
                            )
                        )
                    else:
                        ru_blocks.append(
                            ParagraphBlock(
                                block_id=seg.segment_id,
                                children=list(seg.target_inline),
                            )
                        )
                ru_ir = PageIRV1(
                    document_id=doc, page_id="p0001", page_number=1,
                    language=LanguageCode.RU, dimensions_pt=en_ir.dimensions_pt,
                    blocks=ru_blocks, reading_order=en_ir.reading_order,  # type: ignore[arg-type]
                )
                store.put_json(
                    document_id=doc, schema_family="page_ir.v1.ru",
                    scope="page", entity_id="p0001", data=ru_ir,
                )

            elif stage_name == "render":
                assert ru_ir is not None
                render_page = build_render_page(ru_ir)
                store.put_json(
                    document_id=doc, schema_family="render_page.v1",
                    scope="page", entity_id="p0001", data=render_page,
                )

            elif stage_name == "qa":
                assert en_ir is not None and ru_ir is not None and render_page is not None
                qa_records = evaluate_icon_count(en_ir, ru_ir, render_page)
                if qa_records:
                    has_errors = True
                    for r in qa_records:
                        typer.echo(f"    {r.severity.value}: {r.message}", err=True)
                else:
                    typer.echo("    QA passed: no icon count issues")

        except Exception as e:
            typer.echo(f"    FAILED: {e}", err=True)
            has_errors = True
            break

    status = "failed" if has_errors else "completed"
    finish_run(conn, run_id=run_id, status=status)
    conn.close()

    if has_errors:
        typer.echo(f"Run {run_id} finished with errors.")
        raise typer.Exit(1)
    else:
        typer.echo(f"Run {run_id} completed successfully.")
