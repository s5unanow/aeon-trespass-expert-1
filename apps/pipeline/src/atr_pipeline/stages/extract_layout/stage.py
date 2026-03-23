"""Extract layout stage — produce LayoutPageV1 from native pages + rasters."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
from atr_pipeline.stages.extract_layout.docling_adapter import extract_layout_stub
from atr_pipeline.stages.extract_layout.fallback_stub import ocr_fallback_stub
from atr_schemas.enums import StageScope
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1


class ExtractLayoutResult(BaseModel):
    """Summary of layout extraction across all pages."""

    document_id: str
    pages_processed: int = Field(default=0, ge=0)
    hard_pages: int = Field(default=0, ge=0)
    total_zones: int = Field(default=0, ge=0)


class ExtractLayoutStage:
    """Extract layout evidence per page using Docling (primary) + OCR fallback.

    Reads ``NativePageV1`` artifacts and page rasters from the store,
    runs layout extraction, and stores ``LayoutPageV1`` per page.
    """

    @property
    def name(self) -> str:
        return "extract_layout"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> ExtractLayoutResult:
        raster_provider = PageRasterProvider(
            store=ctx.artifact_store,
            document_id=ctx.document_id,
            pyramid_dpi=ctx.config.extraction.raster.pyramid_dpi,
        )

        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))
        pages_processed = 0
        hard_pages = 0
        total_zones = 0

        for page_id in page_ids:
            native = self._load_native_page(ctx, page_id)
            if native is None:
                ctx.logger.warning("Skipping %s: missing native page", page_id)
                continue

            raster = raster_provider.get_raster(page_id)
            raster_path = str(raster) if raster else None
            layout = self._extract(ctx, native, raster_path)

            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="layout_page.v1",
                scope="page",
                entity_id=page_id,
                data=layout,
            )

            pages_processed += 1
            total_zones += len(layout.zones)
            if layout.difficulty and layout.difficulty.hard_page:
                hard_pages += 1

        ctx.logger.info(
            "Layout extracted for %d pages (%d hard, %d zones)",
            pages_processed,
            hard_pages,
            total_zones,
        )

        return ExtractLayoutResult(
            document_id=ctx.document_id,
            pages_processed=pages_processed,
            hard_pages=hard_pages,
            total_zones=total_zones,
        )

    @staticmethod
    def _extract(
        ctx: StageContext,
        native: NativePageV1,
        raster_path: str | None,
    ) -> LayoutPageV1:
        """Run primary extractor, fall back on failure."""
        try:
            img = Path(raster_path) if raster_path else None
            return extract_layout_stub(native, img)
        except Exception:
            ctx.logger.warning(
                "Primary layout extraction failed for %s, using fallback",
                native.page_id,
                exc_info=True,
            )
            return ocr_fallback_stub(native)

    @staticmethod
    def _resolve_page_ids(ctx: StageContext) -> list[str]:
        """Get page IDs from native page artifacts."""
        native_dir = ctx.artifact_store.root / ctx.document_id / "native_page.v1" / "page"
        if native_dir.exists():
            ids = sorted(d.name for d in native_dir.iterdir() if d.is_dir())
            if ids:
                return ids

        msg = "No native pages found. Run extract_native stage first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_native_page(ctx: StageContext, page_id: str) -> NativePageV1 | None:
        """Load a NativePageV1 from the artifact store."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="native_page.v1",
            scope="page",
            entity_id=page_id,
        )
        return NativePageV1.model_validate(data) if data else None
