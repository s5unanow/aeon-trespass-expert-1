"""Ingest stage — fingerprint PDF, rasterize pages, emit SourceManifestV1."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.rasterizer import render_page_png
from atr_pipeline.stages.ingest.manifest_builder import build_manifest
from atr_pipeline.stages.ingest.pdf_fingerprint import fingerprint_pdf
from atr_schemas.enums import StageScope
from atr_schemas.source_manifest_v1 import SourceManifestV1


class IngestStage:
    """Ingest: register the source PDF, rasterize pages, emit manifest."""

    @property
    def name(self) -> str:
        return "ingest"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> SourceManifestV1:
        pdf_path = ctx.config.source_pdf_path
        if not pdf_path.exists():
            msg = f"Source PDF not found: {pdf_path}"
            raise FileNotFoundError(msg)

        ctx.logger.info("Fingerprinting %s", pdf_path.name)
        sha256, page_count = fingerprint_pdf(pdf_path)

        # Rasterize each page
        dpi = ctx.config.extraction.layout.dpi
        for page_num in range(1, page_count + 1):
            page_id = f"p{page_num:04d}"
            ctx.logger.info("Rasterizing %s at %d DPI", page_id, dpi)
            png_bytes = render_page_png(pdf_path, page_num, dpi=dpi)
            ctx.artifact_store.put_bytes(
                document_id=ctx.document_id,
                schema_family="raster",
                scope="page",
                entity_id=page_id,
                data=png_bytes,
                extension=".png",
            )

        manifest = build_manifest(
            document_id=ctx.document_id,
            source_pdf_sha256=sha256,
            page_count=page_count,
        )
        return manifest
