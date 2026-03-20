"""Ingest stage — fingerprint PDF, rasterize pages, extract images, emit SourceManifestV1."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.image_extractor import extract_page_images
from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
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

        # Build raster provider for multi-DPI pyramid rendering
        raster_provider = PageRasterProvider(
            store=ctx.artifact_store,
            document_id=ctx.document_id,
            pyramid_dpi=ctx.config.extraction.raster.pyramid_dpi,
        )

        all_page_ids = [f"p{n:04d}" for n in range(1, page_count + 1)]
        active_pages = set(ctx.filter_pages(all_page_ids))
        for page_num in range(1, page_count + 1):
            page_id = f"p{page_num:04d}"
            if active_pages and page_id not in active_pages:
                continue
            dpis = raster_provider.pyramid_dpi
            ctx.logger.info("Rasterizing %s at %s DPI", page_id, dpis)
            raster_provider.render_page(
                pdf_path,
                page_num,
                page_id,
                source_pdf_sha256=sha256,
            )

            # Extract embedded images from the page
            images = extract_page_images(pdf_path, page_number=page_num)
            for img in images:
                ctx.logger.info(
                    "Extracted image %s (%dx%d) from %s",
                    img.image_id,
                    img.width_px,
                    img.height_px,
                    page_id,
                )
                ctx.artifact_store.put_bytes(
                    document_id=ctx.document_id,
                    schema_family="image",
                    scope="page",
                    entity_id=img.image_id,
                    data=img.image_bytes,
                    extension=img.extension,
                )

        manifest = build_manifest(
            document_id=ctx.document_id,
            source_pdf_sha256=sha256,
            page_count=page_count,
        )
        return manifest
