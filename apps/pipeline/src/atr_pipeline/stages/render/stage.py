"""Render stage — build render pages, nav, glossary, and search docs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.render.annotation_builder import build_facsimile_annotations
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_pipeline.stages.render.presentation_classifier import classify_presentation_mode
from atr_schemas.enums import StageScope
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.raster_meta_v1 import RasterMetaV1
from atr_schemas.render_page_v1 import RenderFacsimile, RenderNav, RenderPageV1


class RenderResult(BaseModel):
    """Summary of render page generation across all pages."""

    document_id: str
    pages_rendered: int = Field(ge=0)
    page_refs: dict[str, str] = Field(default_factory=dict)
    image_refs: dict[str, str] = Field(default_factory=dict)
    raster_refs: dict[str, dict[int, str]] = Field(default_factory=dict)
    glossary_ref: str = ""
    search_docs_ref: str = ""
    nav_ref: str = ""


class RenderStage:
    """Build render pages from translated (or source) page IR.

    Reads RU ``PageIRV1`` artifacts from the store (falling back to EN IR),
    calls ``build_render_page()`` per page, and stores ``RenderPageV1``
    artifacts.
    """

    @property
    def name(self) -> str:
        return "render"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> RenderResult:
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))
        image_sources, image_refs = self._resolve_images(ctx)
        render_cfg = ctx.config.render
        rendered_pages: list[RenderPageV1] = []
        raster_refs: dict[str, dict[int, str]] = {}

        # First pass: build all render pages
        for page_id in page_ids:
            ir = self._load_page_ir(ctx, page_id)
            if ir is None:
                ctx.logger.warning("Skipping %s: missing page IR", page_id)
                continue
            ctx.logger.info("Building render page for %s", page_id)
            render_page = build_render_page(ir, image_sources=image_sources)

            # Classify presentation mode
            difficulty = self._load_difficulty(ctx, page_id)
            mode = classify_presentation_mode(
                page_id,
                difficulty,
                render_cfg.facsimile_coverage_threshold,
                render_cfg.page_overrides,
            )
            render_page.presentation_mode = mode

            if mode == "facsimile":
                raster_meta = self._load_raster_meta(ctx, page_id)
                if raster_meta and raster_meta.levels:
                    render_page.facsimile = _build_facsimile(raster_meta)
                    for level in raster_meta.levels:
                        raster_refs.setdefault(page_id, {})[level.dpi] = level.relative_path
                elif raster_meta:
                    ctx.logger.warning("Facsimile %s: raster meta has no levels", page_id)
                else:
                    ctx.logger.warning("Facsimile %s: no raster metadata found", page_id)

                # Build translation overlay annotations
                if render_page.facsimile is not None:
                    en_ir = self._load_page_ir_by_lang(ctx, page_id, "en")
                    ru_ir = self._load_page_ir_by_lang(ctx, page_id, "ru")
                    if en_ir is not None:
                        annotations = build_facsimile_annotations(en_ir, ru_ir)
                        render_page.facsimile.annotations = annotations
                        ctx.logger.info("Facsimile %s: %d annotations", page_id, len(annotations))

            # Apply title override or fallback
            override = render_cfg.page_overrides.get(page_id)
            if override and override.title is not None:
                render_page.page.title = override.title
            elif mode == "facsimile" and len(render_page.page.title) <= 2:
                render_page.page.title = f"Page {ir.page_number}"

            rendered_pages.append(render_page)

        # Inject prev/next nav into each page
        self._inject_nav(rendered_pages)

        # Store pages with nav populated
        page_refs: dict[str, str] = {}
        for render in rendered_pages:
            ref = ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="render_page.v1",
                scope="page",
                entity_id=render.page.id,
                data=render,
            )
            page_refs[render.page.id] = ref.relative_path

        ctx.logger.info("Rendered %d pages", len(rendered_pages))

        companion_refs = self._emit_companion_artifacts(ctx, rendered_pages)
        return RenderResult(
            document_id=ctx.document_id,
            pages_rendered=len(rendered_pages),
            page_refs=page_refs,
            image_refs=image_refs,
            raster_refs=raster_refs,
            **companion_refs,
        )

    @staticmethod
    def _emit_companion_artifacts(ctx: StageContext, pages: list[RenderPageV1]) -> dict[str, str]:
        """Emit glossary, search_docs, and nav artifacts."""
        from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
        from atr_pipeline.stages.render.glossary_builder import build_glossary_payload
        from atr_pipeline.stages.render.nav_builder import build_nav_payload
        from atr_pipeline.stages.render.search_builder import build_search_docs

        store = ctx.artifact_store
        doc = ctx.document_id
        refs: dict[str, str] = {}

        glossary_path = ctx.config.repo_root / "configs" / "glossary" / "concepts.toml"
        registry = load_concept_registry(glossary_path) if glossary_path.exists() else None

        glossary = build_glossary_payload(doc, registry, pages)
        r = store.put_json(
            document_id=doc,
            schema_family="glossary_payload.v1",
            scope="document",
            entity_id=doc,
            data=glossary,
        )
        refs["glossary_ref"] = r.relative_path

        search = build_search_docs(doc, pages)
        r = store.put_json(
            document_id=doc,
            schema_family="search_docs.v1",
            scope="document",
            entity_id=doc,
            data=search,
        )
        refs["search_docs_ref"] = r.relative_path

        nav = build_nav_payload(doc, pages)
        r = store.put_json(
            document_id=doc,
            schema_family="nav.v1",
            scope="document",
            entity_id=doc,
            data=nav,
        )
        refs["nav_ref"] = r.relative_path

        ctx.logger.info("Emitted glossary, search_docs, nav artifacts")
        return refs

    @staticmethod
    def _inject_nav(pages: list[RenderPageV1]) -> None:
        """Populate prev/next nav on each render page."""
        for i, page in enumerate(pages):
            page.nav = RenderNav(
                prev=pages[i - 1].page.id if i > 0 else None,
                next=pages[i + 1].page.id if i < len(pages) - 1 else None,
            )

    @staticmethod
    def _resolve_images(ctx: StageContext) -> tuple[dict[str, str], dict[str, str]]:
        """Find image assets in the artifact store.

        Returns:
            A tuple of (image_sources, image_refs) where:
            - image_sources maps asset_id → bundle-relative src for render pages
            - image_refs maps asset_id → artifact-store-relative path for the bundle
        """
        image_dir = ctx.artifact_store.root / ctx.document_id / "image" / "page"
        sources: dict[str, str] = {}
        refs: dict[str, str] = {}
        if not image_dir.exists():
            return sources, refs
        image_exts = {".png", ".jpeg", ".jpg", ".webp", ".gif", ".svg"}
        for asset_dir in sorted(image_dir.iterdir()):
            if not asset_dir.is_dir():
                continue
            files = [f for f in asset_dir.iterdir() if f.suffix in image_exts]
            if not files:
                continue
            img_file = max(files, key=lambda f: f.stat().st_mtime)
            asset_id = asset_dir.name
            sources[asset_id] = f"data/images/{asset_id}{img_file.suffix}"
            refs[asset_id] = str(img_file.relative_to(ctx.artifact_store.root))
        return sources, refs

    @staticmethod
    def _resolve_page_ids(ctx: StageContext) -> list[str]:
        """Get page IDs from RU or EN IR artifacts in the store."""
        for family in ("page_ir.v1.ru", "page_ir.v1.en"):
            ir_dir = ctx.artifact_store.root / ctx.document_id / family / "page"
            if ir_dir.exists():
                ids = sorted(d.name for d in ir_dir.iterdir() if d.is_dir())
                if ids:
                    return ids

        msg = "No IR pages found. Run structure (and optionally translate) first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_page_ir(ctx: StageContext, page_id: str) -> PageIRV1 | None:
        """Load RU PageIRV1 (preferred) or EN PageIRV1 from the artifact store."""
        for family in ("page_ir.v1.ru", "page_ir.v1.en"):
            data = ctx.artifact_store.load_latest_json(
                document_id=ctx.document_id,
                schema_family=family,
                scope="page",
                entity_id=page_id,
            )
            if data is not None:
                return PageIRV1.model_validate(data)
        return None

    @staticmethod
    def _load_page_ir_by_lang(ctx: StageContext, page_id: str, lang: str) -> PageIRV1 | None:
        """Load PageIRV1 for a specific language."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=f"page_ir.v1.{lang}",
            scope="page",
            entity_id=page_id,
        )
        if data is None:
            return None
        return PageIRV1.model_validate(data)

    @staticmethod
    def _load_difficulty(ctx: StageContext, page_id: str) -> DifficultyScoreV1 | None:
        """Load difficulty score from layout page artifact."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="layout_page.v1",
            scope="page",
            entity_id=page_id,
        )
        if data is None:
            return None
        return LayoutPageV1.model_validate(data).difficulty

    @staticmethod
    def _load_raster_meta(ctx: StageContext, page_id: str) -> RasterMetaV1 | None:
        """Load raster metadata for a page."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="raster_meta.v1",
            scope="page",
            entity_id=page_id,
        )
        if data is None:
            return None
        return RasterMetaV1.model_validate(data)


def _build_facsimile(raster_meta: RasterMetaV1) -> RenderFacsimile:
    """Build RenderFacsimile from raster metadata."""
    std = next((lv for lv in raster_meta.levels if lv.dpi == 150), None)
    hires = next((lv for lv in raster_meta.levels if lv.dpi == 300), None)
    level = std or hires or raster_meta.levels[0]
    return RenderFacsimile(
        raster_src=f"rasters/{raster_meta.page_id}__{level.dpi}dpi.png",
        raster_src_hires=(f"rasters/{raster_meta.page_id}__{hires.dpi}dpi.png" if hires else ""),
        width_px=level.width_px,
        height_px=level.height_px,
    )
