"""QA stage — run quality-assurance rules across all pages."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.eval.confidence_policy import load_confidence_bands
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.qa.metrics import compute_qa_metrics, format_metrics_digest
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_pipeline.stages.qa.rules.confidence_band_rule import (
    CODE_QA_REQUIRED,
    evaluate_confidence_band,
)
from atr_pipeline.stages.qa.user_feedback import load_user_feedback_records
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_schemas.enums import QALayer, Severity, StageScope
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
        # 1.3 -> 1.4 (S5U-704): new ``flat_table`` rule flags TableBlocks
        # that lack RenderTableRowBlock structure. The version bump
        # invalidates cached QA runs so previously-missing
        # FLAT_TABLE_NO_ROWS records now appear for the full page set.
        # 1.4 -> 1.5 (S5U-705): ``chart_title_merge_rule`` now writes the
        # real document_id into ``QARecordV1.document_id`` (sourced from
        # ``source_ir.document_id``) instead of the page_id that the S5U-698
        # introduction erroneously plumbed via ``render_page.source_map``.
        # Cached QA records from v1.4 carry the wrong document_id value, so
        # the version bump forces a re-run so downstream consumers that
        # join/group by document_id see the corrected value.
        # 1.5 -> 1.6 (S5U-735): seven more rules (dead_page_ref,
        # decorative_icon, duplicate_content, flat_table, glued_text,
        # leaked_identifier, paragraph_length) now read ``document_id``
        # from the new ``RenderSourceMap.document_id`` field; the
        # chart_title_merge rule is reconciled to the same source.
        # Cached QA records from v1.5 carry the page id in
        # ``QARecordV1.document_id`` for these rules; the bump forces
        # a re-run so per-document rollups see the corrected value.
        return "1.6"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> QASummaryV1:
        # S5U-701 — resolve the FULL published page set from the artifact
        # store BEFORE applying any `--pages` selection.  The dead-page-ref
        # rule uses this set as the authoritative manifest; if we built it
        # from the filtered subset, a partial QA run with ``--pages`` would
        # misclassify every reference to an unselected-but-published page
        # as dead (regression flagged by Codex cross-system review round 1).
        #
        # Round 2 (Codex) flagged a cross-system contract gap: the web
        # reader's ``manifest.json`` is narrower than EN IR — ``export_pages``
        # skips non-facsimile pages with no renderable blocks (see
        # ``scripts/export_to_web.py`` Lines 221-248).  A QA-known page that
        # gets dropped at export time would still be dead from the reader's
        # perspective.  The manifest the QA rule checks against must match
        # the exporter's filter so the suppression set never includes pages
        # the reader will not actually publish.
        all_page_ids = self._resolve_page_ids(ctx)
        publishable_page_ids = self._filter_publishable_pages(ctx, all_page_ids)
        known_page_numbers = _page_ids_to_numbers(publishable_page_ids)
        page_ids = ctx.filter_pages(all_page_ids)

        all_records: list[QARecordV1] = []
        rules = get_all_rules()
        confidence_policy = load_confidence_bands(repo_root=ctx.config.repo_root)
        ctx.logger.info(
            "Loaded confidence-band policy v%d with %d bands",
            confidence_policy.version,
            len(confidence_policy.bands),
        )

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

            page_ctx = QAPageContext(
                source_ir=en_ir,
                target_ir=ru_ir,
                render_page=render,
                known_page_numbers=known_page_numbers,
            )
            records: list[QARecordV1] = []
            for rule in rules:
                records.extend(rule.evaluate(page_ctx))
            if not source_only:
                records.extend(self._load_translation_records(ctx, page_id))
            records.extend(self._load_user_feedback_records(ctx, page_id))
            records.extend(evaluate_confidence_band(en_ir, confidence_policy))
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
        has_qa_required = any(
            r.layer is QALayer.CONFIDENCE and r.code == CODE_QA_REQUIRED and not r.waived
            for r in all_records
        )
        total = counts.info + counts.warning + counts.error + counts.critical

        review_pack_ref = ""
        if blocking or has_qa_required:
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
    def _filter_publishable_pages(ctx: StageContext, page_ids: list[str]) -> list[str]:
        """Return the subset of *page_ids* the web exporter will publish.

        Mirrors the filter in ``scripts/export_to_web.py::export_pages``:
        a page is published iff a render artifact exists for it AND the
        page is either in facsimile mode or has at least one renderable
        block.  This keeps the dead-page-ref suppression manifest aligned
        with what the reader actually sees — a page that EN IR knows
        about but the exporter drops is still dead from the reader's
        perspective and must not be suppressed (Codex REVISE round 2).
        """
        publishable: list[str] = []
        for pid in page_ids:
            data = ctx.artifact_store.load_latest_json(
                document_id=ctx.document_id,
                schema_family="render_page.v1",
                scope="page",
                entity_id=pid,
            )
            if not data:
                # No render artifact → exporter skips it, so it's not in
                # the reader manifest.
                continue
            presentation = data.get("presentation_mode")
            blocks = data.get("blocks") or []
            if presentation == "facsimile" or blocks:
                publishable.append(pid)
        return publishable

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


def _page_ids_to_numbers(page_ids: list[str]) -> frozenset[int]:
    """Convert p0008-style ids to the set of PDF page numbers.

    Invalid or malformed ids are silently skipped; the helper is called from
    the QA stage's initialization path and must never raise.  The rule
    downstream treats a populated set as the authoritative manifest, so
    preserving even partial membership is correct when an id happens to
    be malformed (the manifest-aware branch suppresses less than it could,
    never more).
    """
    numbers: set[int] = set()
    for pid in page_ids:
        # page_id shape: "p" + 4-digit zero-padded number.
        if len(pid) < 2 or not pid.startswith("p"):
            continue
        try:
            numbers.add(int(pid[1:]))
        except ValueError:
            continue
    return frozenset(numbers)
