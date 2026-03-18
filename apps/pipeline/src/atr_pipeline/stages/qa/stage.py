"""QA stage — run quality-assurance rules across all pages."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.qa.rules.icon_count_rule import evaluate_icon_count
from atr_schemas.enums import StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.render_page_v1 import RenderPageV1


class QAResult(BaseModel):
    """Summary of QA checks across all pages."""

    document_id: str
    pages_checked: int = Field(ge=0)
    issues_found: int = Field(ge=0)


class QAStage:
    """Run QA rules across all pages.

    Reads EN IR, RU IR, and render pages from the artifact store,
    evaluates quality rules per page, and returns a summary.
    Raises ``RuntimeError`` if any QA issues are found.
    """

    @property
    def name(self) -> str:
        return "qa"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        return "1.0"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> QAResult:
        page_ids = self._resolve_page_ids(ctx)
        pages_checked = 0
        issues_found = 0

        for page_id in page_ids:
            en_ir = self._load_ir(ctx, "page_ir.v1.en", page_id)
            ru_ir = self._load_ir(ctx, "page_ir.v1.ru", page_id)
            render = self._load_render(ctx, page_id)

            if en_ir is None or ru_ir is None or render is None:
                ctx.logger.warning("Skipping QA for %s: missing artifacts", page_id)
                continue

            records = evaluate_icon_count(en_ir, ru_ir, render)
            for r in records:
                ctx.logger.warning("QA %s: %s", r.severity.value, r.message)
            issues_found += len(records)
            pages_checked += 1

        ctx.logger.info("QA checked %d pages, %d issues found", pages_checked, issues_found)

        if issues_found > 0:
            msg = f"QA failed: {issues_found} issues found across {pages_checked} pages"
            raise RuntimeError(msg)

        return QAResult(
            document_id=ctx.document_id,
            pages_checked=pages_checked,
            issues_found=issues_found,
        )

    @staticmethod
    def _resolve_page_ids(ctx: StageContext) -> list[str]:
        """Get page IDs from EN IR artifacts in the store."""
        ir_dir = ctx.artifact_store.root / ctx.document_id / "page_ir.v1.en" / "page"
        if ir_dir.exists():
            return sorted(d.name for d in ir_dir.iterdir() if d.is_dir())

        msg = "No EN IR pages found. Run structure stage first."
        raise RuntimeError(msg)

    @staticmethod
    def _load_ir(ctx: StageContext, family: str, page_id: str) -> PageIRV1 | None:
        """Load a PageIRV1 from the artifact store."""
        page_dir = ctx.artifact_store.root / ctx.document_id / family / "page" / page_id
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return PageIRV1.model_validate(data)

    @staticmethod
    def _load_render(ctx: StageContext, page_id: str) -> RenderPageV1 | None:
        """Load a RenderPageV1 from the artifact store."""
        page_dir = ctx.artifact_store.root / ctx.document_id / "render_page.v1" / "page" / page_id
        if not page_dir.exists():
            return None
        jsons = sorted(page_dir.glob("*.json"))
        if not jsons:
            return None
        data = json.loads(jsons[-1].read_text())
        return RenderPageV1.model_validate(data)
