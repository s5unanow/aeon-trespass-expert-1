"""Symbols stage — detect symbols on each page via template matching."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.services.pdf.raster_provider import PageRasterProvider
from atr_pipeline.stages.extract_native.stage import ExtractNativeResult
from atr_pipeline.stages.symbols.catalog_loader import load_symbol_catalog
from atr_pipeline.stages.symbols.matcher import TemplateCache, match_symbols
from atr_schemas.enums import StageScope
from atr_schemas.native_page_v1 import NativePageV1


class SymbolsResult(BaseModel):
    """Summary of symbol matching across all pages."""

    document_id: str
    pages_matched: int = Field(ge=0)
    total_symbols: int = Field(ge=0)


class SymbolsStage:
    """Match symbols on all pages in a document.

    Loads the symbol catalog from config, reads native pages and rasters
    from the artifact store, runs ``match_symbols()`` per page, and stores
    a ``SymbolMatchSetV1`` artifact per page.
    """

    @property
    def name(self) -> str:
        return "symbols"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> SymbolsResult:
        catalog_path = ctx.config.symbol_catalog_path
        if not catalog_path or not catalog_path.exists():
            ctx.logger.info("No symbol catalog configured, skipping")
            return SymbolsResult(
                document_id=ctx.document_id,
                pages_matched=0,
                total_symbols=0,
            )

        catalog = load_symbol_catalog(catalog_path)
        tcache = TemplateCache.from_catalog(catalog, repo_root=ctx.config.repo_root)

        raster_provider = PageRasterProvider(
            store=ctx.artifact_store,
            document_id=ctx.document_id,
            pyramid_dpi=ctx.config.extraction.raster.pyramid_dpi,
        )

        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx, input_data))
        pages_matched = 0
        total_symbols = 0

        for page_id in page_ids:
            native = self._load_native_page(ctx, page_id)
            raster_path = raster_provider.get_raster(page_id)

            if native is None or raster_path is None:
                ctx.logger.warning("Skipping %s: missing native or raster", page_id)
                continue

            ctx.logger.info("Matching symbols on %s", page_id)
            matches = match_symbols(
                native,
                raster_path,
                catalog,
                repo_root=ctx.config.repo_root,
                template_cache=tcache,
            )

            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="symbol_match_set.v1",
                scope="page",
                entity_id=page_id,
                data=matches,
            )
            pages_matched += 1
            total_symbols += len(matches.matches)

        ctx.logger.info("Matched %d symbols across %d pages", total_symbols, pages_matched)
        return SymbolsResult(
            document_id=ctx.document_id,
            pages_matched=pages_matched,
            total_symbols=total_symbols,
        )

    @staticmethod
    def _resolve_page_ids(ctx: StageContext, input_data: BaseModel | None) -> list[str]:
        """Get page IDs from input or artifact store."""
        if isinstance(input_data, ExtractNativeResult):
            return input_data.page_ids

        # Fallback: scan native_page.v1 artifacts in store
        native_dir = ctx.artifact_store.root / ctx.document_id / "native_page.v1" / "page"
        if native_dir.exists():
            return sorted(d.name for d in native_dir.iterdir() if d.is_dir())

        msg = "No page IDs available. Run extract_native first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_native_page(ctx: StageContext, page_id: str) -> NativePageV1 | None:
        """Load a NativePageV1 from the artifact store."""
        page_dir = ctx.artifact_store.root / ctx.document_id / "native_page.v1" / "page" / page_id
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return NativePageV1.model_validate(data)
