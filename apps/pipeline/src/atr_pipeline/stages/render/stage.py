"""Render stage — build render pages, nav, glossary, and search docs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import RenderNav, RenderPageV1


class RenderResult(BaseModel):
    """Summary of render page generation across all pages."""

    document_id: str
    pages_rendered: int = Field(ge=0)
    page_refs: dict[str, str] = Field(default_factory=dict)
    image_refs: dict[str, str] = Field(default_factory=dict)
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
        rendered_pages: list[RenderPageV1] = []

        # First pass: build all render pages
        for page_id in page_ids:
            ir = self._load_page_ir(ctx, page_id)
            if ir is None:
                ctx.logger.warning("Skipping %s: missing page IR", page_id)
                continue
            ctx.logger.info("Building render page for %s", page_id)
            rendered_pages.append(build_render_page(ir, image_sources=image_sources))

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
