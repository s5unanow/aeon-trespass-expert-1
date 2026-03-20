"""Structure stage — build page IR from native evidence and symbol matches."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.structure.block_builder import build_page_ir_simple
from atr_pipeline.stages.structure.furniture import FurnitureMap, detect_furniture
from atr_pipeline.stages.structure.real_block_builder import build_page_ir_real
from atr_schemas.common import ConfidenceMetrics, ProvenanceRef
from atr_schemas.enums import StageScope
from atr_schemas.layout_page_v1 import LayoutPageV1
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.symbol_match_set_v1 import SymbolMatchSetV1


class StructureResult(BaseModel):
    """Summary of structure recovery across all pages."""

    document_id: str
    pages_built: int = Field(ge=0)
    total_blocks: int = Field(ge=0)
    hard_pages: int = Field(ge=0, default=0)


class StructureStage:
    """Build page IR from native evidence and symbol matches.

    Uses ``structure_builder`` config to select the builder function
    (``"simple"`` for walking skeleton, ``"real"`` for full documents).
    Reads native pages and symbol matches from the artifact store.
    Stores one ``PageIRV1`` (EN) artifact per page.
    """

    @property
    def name(self) -> str:
        return "structure"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.1"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> StructureResult:
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx, input_data))
        builder = ctx.config.document.structure_builder
        pages_built = 0
        total_blocks = 0
        hard_pages = 0

        # Pre-load all native pages for furniture detection (reused below)
        furniture_map = FurnitureMap()
        native_cache: dict[str, NativePageV1] = {}
        if builder == "real":
            for pid in page_ids:
                page = self._load_native_page(ctx, pid)
                if page is not None:
                    native_cache[pid] = page
            furniture_map = detect_furniture(list(native_cache.values()))
            if furniture_map.has_furniture:
                ctx.logger.info(
                    "Detected %d furniture regions (%d spans)",
                    len(furniture_map.repeated_regions),
                    len(furniture_map.stripped_span_ids),
                )

        for page_id in page_ids:
            native = native_cache.get(page_id) or self._load_native_page(ctx, page_id)
            if native is None:
                ctx.logger.warning("Skipping %s: missing native page", page_id)
                continue

            symbols = self._load_symbol_matches(ctx, page_id)
            layout = self._load_layout_page(ctx, page_id)

            # Determine evidence path from layout difficulty
            route = "R1"
            is_hard = False
            if layout and layout.difficulty:
                route = layout.difficulty.recommended_route
                is_hard = layout.difficulty.hard_page

            if is_hard:
                hard_pages += 1
                ctx.logger.warning(
                    "Hard page %s (route=%s), using native-only path",
                    page_id,
                    route,
                )

            ctx.logger.info(
                "Building IR for %s (builder=%s, route=%s)",
                page_id,
                builder,
                route,
            )
            if builder == "simple":
                sym = symbols or SymbolMatchSetV1(
                    document_id=ctx.document_id,
                    page_id=page_id,
                )
                ir = build_page_ir_simple(native, sym)
            else:
                ir = build_page_ir_real(
                    native,
                    symbols,
                    config=ctx.config.structure,
                    furniture=furniture_map,
                )

            # Record evidence path and confidence from layout scoring
            ir.provenance = ProvenanceRef(
                extractor="structure",
                version=self.version,
                evidence_ids=[f"route:{route}"],
            )
            if layout and layout.difficulty:
                d = layout.difficulty
                ir.confidence = ConfidenceMetrics(
                    native_text_coverage=d.native_text_coverage,
                    page_confidence=d.extractor_agreement,
                )

            ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="page_ir.v1.en",
                scope="page",
                entity_id=page_id,
                data=ir,
            )
            pages_built += 1
            total_blocks += len(ir.blocks)

        ctx.logger.info(
            "Built %d blocks across %d pages (%d hard)",
            total_blocks,
            pages_built,
            hard_pages,
        )
        return StructureResult(
            document_id=ctx.document_id,
            pages_built=pages_built,
            total_blocks=total_blocks,
            hard_pages=hard_pages,
        )

    @staticmethod
    def _resolve_page_ids(
        ctx: StageContext,
        input_data: BaseModel | None,
    ) -> list[str]:
        """Get page IDs from the artifact store."""
        native_dir = ctx.artifact_store.root / ctx.document_id / "native_page.v1" / "page"
        if native_dir.exists():
            return sorted(d.name for d in native_dir.iterdir() if d.is_dir())

        msg = "No native pages found. Run extract_native first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_native_page(
        ctx: StageContext,
        page_id: str,
    ) -> NativePageV1 | None:
        """Load a NativePageV1 from the artifact store."""
        page_dir = ctx.artifact_store.root / ctx.document_id / "native_page.v1" / "page" / page_id
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return NativePageV1.model_validate(data)

    @staticmethod
    def _load_symbol_matches(
        ctx: StageContext,
        page_id: str,
    ) -> SymbolMatchSetV1 | None:
        """Load symbol matches from the artifact store, if available."""
        page_dir = (
            ctx.artifact_store.root / ctx.document_id / "symbol_match_set.v1" / "page" / page_id
        )
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return SymbolMatchSetV1.model_validate(data)

    @staticmethod
    def _load_layout_page(
        ctx: StageContext,
        page_id: str,
    ) -> LayoutPageV1 | None:
        """Load layout evidence from the artifact store, if available."""
        page_dir = ctx.artifact_store.root / ctx.document_id / "layout_page.v1" / "page" / page_id
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return LayoutPageV1.model_validate(data)
