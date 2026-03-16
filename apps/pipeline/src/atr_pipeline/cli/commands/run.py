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
        conn, run_id=run_id, document_id=doc,
        pipeline_version=config.pipeline.version, config_hash="",
    )

    stages = resolve_stage_range(from_stage=from_stage, to_stage=to_stage)
    typer.echo(f"Running stages: {' → '.join(stages)}")

    # Lazy imports
    from atr_pipeline.services.llm.factory import create_translator
    from atr_pipeline.services.pdf.rasterizer import render_page_png
    from atr_pipeline.stages.extract_native.pymupdf_extractor import extract_native_page
    from atr_pipeline.stages.ingest.manifest_builder import build_manifest
    from atr_pipeline.stages.ingest.pdf_fingerprint import fingerprint_pdf
    from atr_pipeline.stages.render.page_builder import build_render_page
    from atr_pipeline.stages.structure.block_builder import build_page_ir_simple
    from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
    from atr_pipeline.stages.symbols.catalog_loader import load_symbol_catalog
    from atr_pipeline.stages.symbols.matcher import TemplateCache, match_symbols
    from atr_pipeline.stages.translation.planner import build_translation_batch
    from atr_pipeline.stages.translation.validator import validate_translation
    from atr_schemas.source_manifest_v1 import SourceManifestV1

    # Determine page count and whether this is the walking skeleton
    is_walking_skeleton = doc == "walking_skeleton"

    # Accumulated state
    manifest: SourceManifestV1 | None = None
    native_pages: dict[str, object] = {}
    symbol_matches_map: dict[str, object] = {}
    en_ir_map: dict[str, object] = {}
    ru_ir_map: dict[str, object] = {}
    render_pages: dict[str, object] = {}
    has_errors = False

    # Get page count from PDF for all stage entry points
    _, total_page_count = fingerprint_pdf(config.source_pdf_path)

    # Load existing artifacts if starting from a mid-pipeline stage
    if from_stage != "ingest":
        _load_existing_artifacts(
            store, doc, total_page_count,
            stages, native_pages, en_ir_map,
            extract_native_page, config, build_page_ir_real,
        )

    for stage_name in stages:
        typer.echo(f"  [{stage_name}]")
        try:
            if stage_name == "ingest":
                sha256, page_count = fingerprint_pdf(config.source_pdf_path)
                manifest = build_manifest(
                    document_id=doc, source_pdf_sha256=sha256,
                    page_count=page_count,
                )
                dpi = config.extraction.layout.dpi
                typer.echo(f"    Rasterizing {page_count} pages at {dpi} DPI...")
                for pnum in range(1, page_count + 1):
                    pid = f"p{pnum:04d}"
                    png_bytes = render_page_png(
                        config.source_pdf_path, pnum, dpi=dpi,
                    )
                    store.put_bytes(
                        document_id=doc, schema_family="raster",
                        scope="page", entity_id=pid,
                        data=png_bytes, extension=".png",
                    )
                store.put_json(
                    document_id=doc, schema_family="source_manifest",
                    scope="document", entity_id=doc, data=manifest,
                )
                typer.echo(f"    {page_count} pages ingested")

            elif stage_name == "extract_native":
                if manifest:
                    page_count = manifest.page_count
                else:
                    _, page_count = fingerprint_pdf(config.source_pdf_path)
                for pnum in range(1, page_count + 1):
                    pid = f"p{pnum:04d}"
                    native = extract_native_page(
                        config.source_pdf_path, page_number=pnum,
                        document_id=doc,
                    )
                    native_pages[pid] = native
                    store.put_json(
                        document_id=doc, schema_family="native_page.v1",
                        scope="page", entity_id=pid, data=native,
                    )
                typer.echo(f"    Extracted {len(native_pages)} pages")

            elif stage_name == "symbols":
                catalog_path = config.symbol_catalog_path
                if catalog_path and catalog_path.exists():
                    catalog = load_symbol_catalog(catalog_path)
                    tcache = TemplateCache.from_catalog(
                        catalog, repo_root=config.repo_root,
                    )
                    for pid, native in native_pages.items():
                        raster_dir = store.root / doc / "raster" / "page" / pid
                        rasters = list(raster_dir.glob("*.png"))
                        if rasters:
                            matches = match_symbols(
                                native, rasters[0], catalog,  # type: ignore[arg-type]
                                repo_root=config.repo_root,
                                template_cache=tcache,
                            )
                            symbol_matches_map[pid] = matches
                            store.put_json(
                                document_id=doc,
                                schema_family="symbol_match_set.v1",
                                scope="page", entity_id=pid, data=matches,
                            )
                    matched = sum(
                        len(m.matches)  # type: ignore[union-attr]
                        for m in symbol_matches_map.values()
                    )
                    typer.echo(
                        f"    {matched} symbols matched across "
                        f"{len(symbol_matches_map)} pages"
                    )
                else:
                    typer.echo("    No symbol catalog configured, skipping")

            elif stage_name == "structure":
                for pid, native in native_pages.items():
                    sym = symbol_matches_map.get(pid)
                    if is_walking_skeleton:
                        ir = build_page_ir_simple(native, sym)  # type: ignore[arg-type]
                    else:
                        ir = build_page_ir_real(native, sym)  # type: ignore[arg-type]
                    en_ir_map[pid] = ir
                    store.put_json(
                        document_id=doc, schema_family="page_ir.v1.en",
                        scope="page", entity_id=pid, data=ir,
                    )
                total_blocks = sum(
                    len(ir.blocks) for ir in en_ir_map.values()  # type: ignore[union-attr]
                )
                typer.echo(
                    f"    {total_blocks} blocks across {len(en_ir_map)} pages"
                )

            elif stage_name == "translate":
                # Load concept registry if available
                from pathlib import Path as _Path

                from atr_pipeline.stages.glossary.registry_loader import (
                    load_concept_registry,
                )

                concept_reg = None
                glossary_path = config.repo_root / "configs" / "glossary" / "concepts.toml"
                if glossary_path.exists():
                    concept_reg = load_concept_registry(glossary_path)

                # Use mock for walking skeleton, configured provider otherwise
                if is_walking_skeleton:
                    from atr_pipeline.config.models import TranslationConfig

                    mock_cfg = TranslationConfig(provider="mock")
                    translator = create_translator(mock_cfg)
                else:
                    translator = create_translator(
                        config.translation,
                        concept_registry=concept_reg,
                    )

                _translate_pages(
                    en_ir_map, ru_ir_map, store, doc,
                    translator, build_translation_batch,
                    validate_translation, typer, concept_reg,
                )

            elif stage_name == "render":
                for pid in (ru_ir_map if ru_ir_map else en_ir_map):
                    ir = ru_ir_map.get(pid) or en_ir_map.get(pid)
                    if ir:
                        render = build_render_page(ir)  # type: ignore[arg-type]
                        render_pages[pid] = render
                        store.put_json(
                            document_id=doc,
                            schema_family="render_page.v1",
                            scope="page", entity_id=pid, data=render,
                        )
                typer.echo(f"    {len(render_pages)} render pages built")

            elif stage_name == "qa":
                typer.echo("    QA checks (icon count parity)...")
                from atr_pipeline.stages.qa.rules.icon_count_rule import (
                    evaluate_icon_count,
                )

                qa_issues = 0
                for pid in en_ir_map:
                    en = en_ir_map.get(pid)
                    ru = ru_ir_map.get(pid)
                    rp = render_pages.get(pid)
                    if en and ru and rp:
                        records = evaluate_icon_count(en, ru, rp)  # type: ignore[arg-type]
                        qa_issues += len(records)
                        for r in records:
                            typer.echo(
                                f"    {r.severity.value}: {r.message}",
                                err=True,
                            )
                if qa_issues:
                    has_errors = True
                    typer.echo(f"    {qa_issues} QA issues found")
                else:
                    typer.echo("    QA passed")

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


def _translate_pages(
    en_ir_map: dict[str, object],
    ru_ir_map: dict[str, object],
    store: ArtifactStore,
    doc: str,
    translator: object,
    build_translation_batch: object,
    validate_translation: object,
    typer: object,
    concept_registry: object = None,
) -> None:
    """Translate all pages using the provided adapter."""
    from atr_schemas.concept_registry_v1 import ConceptRegistryV1
    from atr_schemas.enums import LanguageCode
    from atr_schemas.page_ir_v1 import (
        CalloutBlock,
        CaptionBlock,
        HeadingBlock,
        ListBlock,
        ListItemBlock,
        PageIRV1,
        ParagraphBlock,
        TableBlock,
    )
    from atr_schemas.translation_batch_v1 import TranslationBatchV1

    from atr_pipeline.services.llm.base import TranslatorAdapter
    from atr_pipeline.stages.translation.validator import (
        validate_translation as _validate,
    )

    _BLOCK_TYPE_MAP = {
        "heading": HeadingBlock,
        "paragraph": ParagraphBlock,
        "list": ListBlock,
        "list_item": ListItemBlock,
        "table": TableBlock,
        "callout": CalloutBlock,
        "caption": CaptionBlock,
    }

    for pid, en_ir in en_ir_map.items():
        batch: TranslationBatchV1 = build_translation_batch(  # type: ignore[operator]
            en_ir, concept_registry=concept_registry,
        )
        result = translator.translate_batch(batch)  # type: ignore[union-attr]
        errors = validate_translation(  # type: ignore[operator]
            batch, result, concept_registry=concept_registry,
        )
        if errors:
            for e in errors:
                typer.echo(f"    WARN: {e}", err=True)  # type: ignore[union-attr]

        ru_blocks = []
        for seg in result.segments:
            src_block = next(
                (b for b in en_ir.blocks if b.block_id == seg.segment_id),  # type: ignore[union-attr]
                None,
            )
            if src_block is None:
                continue

            block_cls = _BLOCK_TYPE_MAP.get(src_block.type, ParagraphBlock)
            kwargs: dict[str, object] = {
                "block_id": seg.segment_id,
                "children": list(seg.target_inline),
            }
            if block_cls is HeadingBlock:
                kwargs["level"] = getattr(src_block, "level", 2)
            ru_blocks.append(block_cls(**kwargs))  # type: ignore[arg-type]

        ru_ir = PageIRV1(
            document_id=doc, page_id=pid,
            page_number=en_ir.page_number,  # type: ignore[union-attr]
            language=LanguageCode.RU,
            dimensions_pt=en_ir.dimensions_pt,  # type: ignore[union-attr]
            blocks=ru_blocks,  # type: ignore[arg-type]
            reading_order=en_ir.reading_order,  # type: ignore[union-attr]
        )
        ru_ir_map[pid] = ru_ir
        store.put_json(
            document_id=doc, schema_family="page_ir.v1.ru",
            scope="page", entity_id=pid, data=ru_ir,
        )
    typer.echo(f"    Translated {len(ru_ir_map)} pages")  # type: ignore[union-attr]


def _load_existing_artifacts(
    store: ArtifactStore,
    doc: str,
    total_page_count: int,
    stages: list[str],
    native_pages: dict[str, object],
    en_ir_map: dict[str, object],
    extract_native_page: object,
    config: object,
    build_page_ir_real: object,
) -> None:
    """Load existing artifacts from prior runs when starting mid-pipeline."""
    import json

    from atr_schemas.native_page_v1 import NativePageV1
    from atr_schemas.page_ir_v1 import PageIRV1

    # If structure or later stages need native pages, load or extract them
    needs_native = any(s in stages for s in ["structure", "symbols"])
    needs_en_ir = any(s in stages for s in ["translate", "render", "qa"])

    if needs_native and not native_pages:
        native_dir = store.root / doc / "native_page.v1" / "page"
        if native_dir.exists():
            for page_dir in sorted(native_dir.iterdir()):
                if page_dir.is_dir():
                    jsons = list(page_dir.glob("*.json"))
                    if jsons:
                        data = json.loads(jsons[0].read_text())
                        native_pages[page_dir.name] = NativePageV1.model_validate(data)
        # If still empty, extract fresh
        if not native_pages:
            for pnum in range(1, total_page_count + 1):
                pid = f"p{pnum:04d}"
                native = extract_native_page(  # type: ignore[operator]
                    config.source_pdf_path,  # type: ignore[union-attr]
                    page_number=pnum, document_id=doc,
                )
                native_pages[pid] = native

    if needs_en_ir and not en_ir_map:
        ir_dir = store.root / doc / "page_ir.v1.en" / "page"
        if ir_dir.exists():
            for page_dir in sorted(ir_dir.iterdir()):
                if page_dir.is_dir():
                    jsons = list(page_dir.glob("*.json"))
                    if jsons:
                        data = json.loads(jsons[0].read_text())
                        en_ir_map[page_dir.name] = PageIRV1.model_validate(data)
