"""Extract layout stage — produce LayoutPageV1 from native pages + rasters."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
from atr_pipeline.stages.extract_layout.docling_adapter import extract_layout_docling
from atr_pipeline.stages.extract_layout.paddleocr_adapter import extract_layout_ocr
from atr_schemas.enums import StageScope
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1
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
        # S5U-589 1.0 -> 1.1: LayoutPageV1 persists `extraction_path` per page.
        # S5U-580 1.1 -> 1.2: difficulty.extractor_agreement carries a real
        # word-zone recall metric (was hardcoded 1.0 — every cached pre-S5U-580
        # event would report full agreement and never fire the R3 route).
        return "1.2"

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
        """Run primary extractor; escalate to OCR on hard pages or primary failure.

        Tags the returned layout with ``extraction_path`` so downstream
        stages (StructureStage) can attribute fallback provenance to the
        blocks they emit. S5U-589 — one of:

        * ``"primary"``: clean Docling result kept (no OCR needed, or OCR
          produced nothing usable so we fell back to the primary's zones).
        * ``"ocr_fallback"``: OCR layout was selected because either the
          primary failed entirely or it flagged the page as ``hard_page``,
          and the OCR result has zones we can use.
        * ``"extraction_failed"``: both primary and OCR produced nothing;
          we synthesize a degenerate marker layout so the page never
          silently presents as a clean R1.
        """
        img = Path(raster_path) if raster_path else None
        dpi = ctx.config.extraction.layout.dpi

        primary: LayoutPageV1 | None = None
        try:
            primary = extract_layout_docling(native, img, dpi=dpi)
        except Exception:
            ctx.logger.warning(
                "Primary layout extraction failed for %s, escalating to OCR",
                native.page_id,
                exc_info=True,
            )

        if not ExtractLayoutStage._needs_ocr(primary):
            assert primary is not None  # _needs_ocr returns True when primary is None
            primary.extraction_path = "primary"
            return primary

        try:
            ocr = extract_layout_ocr(native, img, dpi=dpi)
        except Exception:
            ctx.logger.warning(
                "OCR fallback failed for %s",
                native.page_id,
                exc_info=True,
            )
            ocr = None

        if ocr is not None and ocr.zones:
            ctx.logger.info("Using OCR layout for hard page %s", native.page_id)
            ocr.extraction_path = "ocr_fallback"
            return ocr

        if primary is not None:
            # OCR was attempted (page was flagged hard) but didn't produce
            # usable zones; we keep the primary's data. Mark as "primary"
            # because the bytes the structure stage will see came from the
            # primary extractor — OCR did not influence the output.
            primary.extraction_path = "primary"
            return primary

        ctx.logger.warning(
            "Layout extraction failed for %s (no primary, no OCR zones); "
            "marking as hard page with extraction-failure difficulty",
            native.page_id,
        )
        return ExtractLayoutStage._failed_extraction_layout(native)

    @staticmethod
    def _failed_extraction_layout(native: NativePageV1) -> LayoutPageV1:
        """Build a LayoutPageV1 marking that both primary and OCR extraction failed.

        The difficulty is populated so the page is visible to QA/review as a
        hard-routed, low-confidence page — never as a silent R1 with
        ``page_confidence=1.0``.
        """
        return LayoutPageV1(
            document_id=native.document_id,
            page_id=native.page_id,
            difficulty=DifficultyScoreV1(
                page_id=native.page_id,
                native_text_coverage=0.0,
                extractor_agreement=0.0,
                hard_page=True,
                recommended_route="R2",
            ),
            extraction_path="extraction_failed",
        )

    @staticmethod
    def _needs_ocr(primary: LayoutPageV1 | None) -> bool:
        """True when the primary layout is missing or flagged as a hard page."""
        if primary is None:
            return True
        return primary.difficulty is not None and primary.difficulty.hard_page

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
