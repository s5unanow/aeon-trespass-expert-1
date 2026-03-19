"""QA stage — run quality-assurance rules across all pages."""

from __future__ import annotations

import json

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_schemas.enums import Severity, StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts
from atr_schemas.render_page_v1 import RenderPageV1


class QAStage:
    """Run QA rules across all pages.

    Reads EN IR, RU IR, and render pages from the artifact store,
    evaluates quality rules per page, persists individual QA records,
    and returns a ``QASummaryV1`` with severity counts and blocking status.
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

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> QASummaryV1:
        page_ids = self._resolve_page_ids(ctx)
        all_records: list[QARecordV1] = []

        for page_id in page_ids:
            en_ir = self._load_ir(ctx, "page_ir.v1.en", page_id)
            ru_ir = self._load_ir(ctx, "page_ir.v1.ru", page_id)
            render = self._load_render(ctx, page_id)

            if en_ir is None or ru_ir is None or render is None:
                ctx.logger.warning("Skipping QA for %s: missing artifacts", page_id)
                continue

            page_ctx = QAPageContext(source_ir=en_ir, target_ir=ru_ir, render_page=render)
            records: list[QARecordV1] = []
            for rule in get_all_rules():
                records.extend(rule.evaluate(page_ctx))
            for r in records:
                ctx.logger.warning("QA %s: %s", r.severity.value, r.message)
            all_records.extend(records)

        record_refs = self._persist_records(ctx, all_records)
        counts = _tally_severities(all_records)
        block_on = set(ctx.config.qa.block_publish_on)
        blocking = any(r.severity.value in block_on for r in all_records)
        total = counts.info + counts.warning + counts.error + counts.critical

        ctx.logger.info("QA found %d issues, blocking=%s", total, blocking)

        return QASummaryV1(
            document_id=ctx.document_id,
            run_id=ctx.run_id,
            counts=counts,
            blocking=blocking,
            record_refs=record_refs,
        )

    @staticmethod
    def _persist_records(ctx: StageContext, records: list[QARecordV1]) -> list[str]:
        """Persist individual QA records and return their artifact refs."""
        refs: list[str] = []
        for record in records:
            ref = ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="qa_record.v1",
                scope="page",
                entity_id=record.page_id or ctx.document_id,
                data=record,
            )
            refs.append(ref.relative_path)
        return refs

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


def _tally_severities(records: list[QARecordV1]) -> SeverityCounts:
    """Count records by severity level."""
    counts = SeverityCounts()
    for r in records:
        if r.severity == Severity.INFO:
            counts.info += 1
        elif r.severity == Severity.WARNING:
            counts.warning += 1
        elif r.severity == Severity.ERROR:
            counts.error += 1
        elif r.severity == Severity.CRITICAL:
            counts.critical += 1
    return counts
