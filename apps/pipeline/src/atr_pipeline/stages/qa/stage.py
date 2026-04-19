"""QA stage — run quality-assurance rules across all pages."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.qa.metrics import compute_qa_metrics, format_metrics_digest
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_pipeline.stages.qa.user_feedback import load_user_feedback_records
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_schemas.enums import Severity, StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1, SeverityCounts
from atr_schemas.render_page_v1 import RenderPageV1
from atr_schemas.translation_qa_record_set_v1 import TranslationQARecordSetV1


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
        # Bumped to "1.1" by S5U-640 to invalidate pre-S5U-597 cache entries
        # so cached QA events re-run and emit the qa_metrics.json artifact
        # that S5U-597 declared as a success criterion. The executor's cache
        # key includes this version string; bumping it makes every existing
        # cached event miss exactly once, then re-cache under the new key
        # with metrics on disk.
        return "1.1"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> QASummaryV1:
        page_ids = ctx.filter_pages(self._resolve_page_ids(ctx))
        all_records: list[QARecordV1] = []
        rules = get_all_rules()

        source_only = ctx.edition == "en"
        if source_only:
            ctx.logger.info("QA running in source-only mode (edition=en)")

        for page_id in page_ids:
            en_ir = self._load_ir(ctx, "page_ir.v1.en", page_id)
            ru_ir = self._load_ir(ctx, "page_ir.v1.ru", page_id) if not source_only else en_ir
            render = self._load_render(ctx, page_id)

            if en_ir is None or ru_ir is None or render is None:
                ctx.logger.warning("Skipping QA for %s: missing artifacts", page_id)
                continue

            page_ctx = QAPageContext(source_ir=en_ir, target_ir=ru_ir, render_page=render)
            records: list[QARecordV1] = []
            for rule in rules:
                records.extend(rule.evaluate(page_ctx))
            if not source_only:
                records.extend(self._load_translation_records(ctx, page_id))
            records.extend(self._load_user_feedback_records(ctx, page_id))
            for r in records:
                ctx.logger.warning("QA %s: %s", r.severity.value, r.message)
            all_records.extend(records)

        waivers_dir = ctx.config.repo_root / ctx.config.qa.waivers_dir
        waivers = load_waivers(waivers_dir, ctx.document_id)
        if waivers:
            ctx.logger.info("Loaded %d waivers for %s", len(waivers), ctx.document_id)
        all_records = apply_waivers(all_records, waivers)

        record_refs = self._persist_records(ctx, all_records)
        counts = _tally_severities([r for r in all_records if not r.waived])
        waived_counts = _tally_severities([r for r in all_records if r.waived])
        block_on = set(ctx.config.qa.block_publish_on)
        blocking = any(r.severity.value in block_on and not r.waived for r in all_records)
        total = counts.info + counts.warning + counts.error + counts.critical

        review_pack_ref = ""
        if blocking:
            pack = build_review_pack(
                document_id=ctx.document_id,
                run_id=ctx.run_id,
                records=all_records,
                block_on=block_on,
            )
            ref = ctx.artifact_store.put_json(
                document_id=ctx.document_id,
                schema_family="review_pack.v1",
                scope="document",
                entity_id=ctx.document_id,
                data=pack,
            )
            review_pack_ref = ref.relative_path
            ctx.logger.info("Review pack written: %s", review_pack_ref)

        ctx.logger.info(
            "QA found %d issues (%d waived), blocking=%s",
            total,
            waived_counts.error + waived_counts.critical,
            blocking,
        )

        metrics = compute_qa_metrics(
            document_id=ctx.document_id,
            run_id=ctx.run_id,
            edition=ctx.edition,
            page_ids=page_ids,
            records=all_records,
            block_on=block_on,
        )
        metrics_ref = ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="qa_metrics.v1",
            scope="document",
            entity_id=ctx.document_id,
            data=metrics,
        )
        ctx.logger.info("QA metrics written: %s", metrics_ref.relative_path)
        ctx.logger.info("%s", format_metrics_digest(metrics))

        return QASummaryV1(
            document_id=ctx.document_id,
            run_id=ctx.run_id,
            edition=ctx.edition,
            counts=counts,
            waived_counts=waived_counts,
            blocking=blocking,
            record_refs=record_refs,
            review_pack_ref=review_pack_ref,
            # S5U-641: bind the specific metrics artifact to this summary so
            # the export layer can pick the ref-bound file instead of the
            # latest-by-mtime metrics, which could be a stray from an
            # interrupted prior run.
            qa_metrics_ref=metrics_ref.relative_path,
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
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family=family,
            scope="page",
            entity_id=page_id,
        )
        return PageIRV1.model_validate(data) if data else None

    @staticmethod
    def _load_translation_records(ctx: StageContext, page_id: str) -> list[QARecordV1]:
        """Load translation-validator QA records persisted by the translate stage."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="translation_qa_record_set.v1",
            scope="page",
            entity_id=page_id,
        )
        if not data:
            return []
        record_set = TranslationQARecordSetV1.model_validate(data)
        return list(record_set.records)

    @staticmethod
    def _load_user_feedback_records(ctx: StageContext, page_id: str) -> list[QARecordV1]:
        """Load reader-feedback QA records persisted by the ingest script.

        When the QA stage runs edition-specific (``ctx.edition`` is ``"en"``
        or ``"ru"``), only that edition's feedback is loaded. When the stage
        runs with the default ``edition="all"`` — still common in mixed
        builds — both editions' feedback is merged so the summary doesn't
        silently drop reader-submitted findings.
        """
        editions = ("en", "ru") if ctx.edition == "all" else (ctx.edition,)
        records: list[QARecordV1] = []
        for edition in editions:
            records.extend(
                load_user_feedback_records(
                    store=ctx.artifact_store,
                    document_id=ctx.document_id,
                    edition=edition,
                    page_id=page_id,
                )
            )
        return records

    @staticmethod
    def _load_render(ctx: StageContext, page_id: str) -> RenderPageV1 | None:
        """Load a RenderPageV1 from the artifact store."""
        data = ctx.artifact_store.load_latest_json(
            document_id=ctx.document_id,
            schema_family="render_page.v1",
            scope="page",
            entity_id=page_id,
        )
        return RenderPageV1.model_validate(data) if data else None


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
