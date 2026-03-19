"""Render stage — build render pages, nav, glossary, and search docs."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import RenderPageV1


class RenderResult(BaseModel):
    """Summary of render page generation across all pages."""

    document_id: str
    pages_rendered: int = Field(ge=0)
    page_refs: dict[str, str] = Field(default_factory=dict)
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
        page_ids = self._resolve_page_ids(ctx)
        pages_rendered = 0
        page_refs: dict[str, str] = {}
        rendered_pages: list[RenderPageV1] = []

        for page_id in page_ids:
            ir = self._load_page_ir(ctx, page_id)
            if ir is None:
                ctx.logger.warning("Skipping %s: missing page IR", page_id)
                continue

            ctx.logger.info("Building render page for %s", page_id)
            render = build_render_page(ir)

            ref = ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="render_page.v1",
                scope="page",
                entity_id=page_id,
                data=render,
            )
            page_refs[page_id] = ref.relative_path
            rendered_pages.append(render)
            pages_rendered += 1

        ctx.logger.info("Rendered %d pages", pages_rendered)

        companion_refs = self._emit_companion_artifacts(ctx, rendered_pages)
        return RenderResult(
            document_id=ctx.document_id,
            pages_rendered=pages_rendered,
            page_refs=page_refs,
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

        nav = build_nav_payload(doc, [p.model_dump() for p in pages])
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
            page_dir = ctx.artifact_store.root / ctx.document_id / family / "page" / page_id
            if not page_dir.exists():
                continue
            jsons = sorted(page_dir.glob("*.json"))
            if jsons:
                data = json.loads(jsons[-1].read_text())
                return PageIRV1.model_validate(data)
        return None
