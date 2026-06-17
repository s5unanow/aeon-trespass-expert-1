"""QA stage — run quality-assurance rules across all pages."""

from __future__ import annotations

from pydantic import BaseModel

from atr_pipeline.eval.confidence_policy import load_confidence_bands
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.qa.fallback_alert import apply_fallback_alert
from atr_pipeline.stages.qa.metrics import compute_qa_metrics, format_metrics_digest
from atr_pipeline.stages.qa.publishable import RenderCache, filter_publishable_pages
from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_pipeline.stages.qa.render_binding import (
    RenderPageRefs,
    load_run_bound_render,
    resolve_run_page_refs,
)
from atr_pipeline.stages.qa.review_pack import build_review_pack
from atr_pipeline.stages.qa.rules.confidence_band_rule import (
    CODE_QA_REQUIRED,
    evaluate_confidence_band,
)
from atr_pipeline.stages.qa.user_feedback import load_user_feedback_records
from atr_pipeline.stages.qa.waivers import apply_waivers, load_waivers
from atr_schemas.enums import QALayer, Severity, StageScope
from atr_schemas.page_ir_v1 import PageIRV1
from atr_schemas.qa_metrics_v1 import FallbackSummary
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
        # Part of the executor cache key; bump on any new observable side-effect
        # of run(). The full bump history (1.0 → 1.11) with per-bump rationale is
        # the authoritative record in
        # ``tests/unit/stages/qa/test_stage_version.py``'s module docstring.
        # Latest: 1.10 -> 1.11 (S5U-1264) — per-page render selection is now
        # run-id-bound (via ``RenderResult.page_refs``) instead of mtime; a
        # cached 1.10 event would re-introduce the cross-run splice the binding
        # prevents. No new artifact write; selection-behavior cache-correctness
        # bump (cf. the S5U-731 1.8 -> 1.9 render-selection bump, S5U-662).
        return "1.11"

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> QASummaryV1:
        # S5U-701 — resolve the FULL published page set BEFORE any `--pages`
        # selection so the dead-page-ref manifest matches the exporter's narrower
        # filter (drops non-facsimile, blockless pages), not the filtered subset.
        all_page_ids = self._resolve_page_ids(ctx)
        # S5U-1264 — resolve the run's render index ONCE so every per-page render
        # select below is run-id-bound, not newest-by-mtime. Empty ⇒ mtime
        # fallback (legacy / partial store); see ``render_binding``.
        page_refs = resolve_run_page_refs(ctx)
        # S5U-1229 — the publishability filter selects+parses every page's
        # render_page.v1; render_cache captures each so the per-page eval loop
        # reuses it (eval pages ⊆ all_page_ids → cache always covers them).
        render_cache: RenderCache = {}
        publishable_page_ids = self._filter_publishable_pages(
            ctx,
            all_page_ids,
            edition=ctx.edition,
            render_cache=render_cache,
            page_refs=page_refs,
        )
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
            render = self._load_render(
                ctx,
                page_id,
                edition=ctx.edition,
                render_cache=render_cache,
                page_refs=page_refs,
            )

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

        # S5U-1226 — run-level provider-fallback aggregate + alert from the
        # per-page translation_meta.v1 artifacts. Feeds qa_metrics; an
        # over-threshold rate emits a document-scope QA record that flows
        # through waivers/blocking like any other finding.
        fallback_summary = apply_fallback_alert(
            store=ctx.artifact_store,
            document_id=ctx.document_id,
            page_ids=page_ids,
            threshold=ctx.config.qa.fallback_rate_warn_threshold,
            severity=ctx.config.qa.fallback_rate_severity,
            logger=ctx.logger,
            all_records=all_records,
        )

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

        metrics_ref = self._write_metrics(
            ctx,
            page_ids=page_ids,
            all_records=all_records,
            block_on=block_on,
            fallback_summary=fallback_summary,
        )

        return QASummaryV1(
            document_id=ctx.document_id,
            run_id=ctx.run_id,
            edition=ctx.edition,
            counts=counts,
            waived_counts=waived_counts,
            blocking=blocking,
            record_refs=record_refs,
            review_pack_ref=review_pack_ref,
            # S5U-641: bind the specific metrics artifact to this summary so the
            # export layer picks the ref-bound file, not a latest-by-mtime stray.
            qa_metrics_ref=metrics_ref,
        )

    @staticmethod
    def _write_metrics(
        ctx: StageContext,
        *,
        page_ids: list[str],
        all_records: list[QARecordV1],
        block_on: set[str],
        fallback_summary: FallbackSummary,
    ) -> str:
        """Compute, attach the fallback aggregate, persist + log ``qa_metrics.v1``."""
        metrics = compute_qa_metrics(
            document_id=ctx.document_id,
            run_id=ctx.run_id,
            edition=ctx.edition,
            page_ids=page_ids,
            records=all_records,
            block_on=block_on,
        )
        # S5U-1226 — attach the run-level fallback aggregate (kept off
        # ``compute_qa_metrics``'s signature to hold its param count).
        metrics.translation_fallback = fallback_summary
        metrics_ref = ctx.artifact_store.put_json(
            document_id=ctx.document_id,
            schema_family="qa_metrics.v1",
            scope="document",
            entity_id=ctx.document_id,
            data=metrics,
        )
        ctx.logger.info("QA metrics written: %s", metrics_ref.relative_path)
        ctx.logger.info("%s", format_metrics_digest(metrics))
        return metrics_ref.relative_path

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
    def _filter_publishable_pages(
        ctx: StageContext,
        page_ids: list[str],
        *,
        edition: str = "",
        render_cache: RenderCache | None = None,
        page_refs: RenderPageRefs | None = None,
    ) -> list[str]:
        """Delegate to ``stages.qa.publishable.filter_publishable_pages``.

        Shared with the CLI ``atr qa`` entrypoint so the two cannot drift on
        "publishable" (S5U-701 / S5U-730). ``edition`` (S5U-731), ``render_cache``
        (S5U-1229) and ``page_refs`` (S5U-1264) pass through unchanged.
        """
        return filter_publishable_pages(
            ctx.artifact_store,
            ctx.document_id,
            page_ids,
            edition=edition,
            render_cache=render_cache,
            page_refs=page_refs,
        )

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

        Edition-specific runs load only that edition's feedback; the default
        ``edition="all"`` merges both so the summary doesn't drop findings.
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
    def _load_render(
        ctx: StageContext,
        page_id: str,
        *,
        edition: str = "",
        render_cache: RenderCache | None = None,
        page_refs: RenderPageRefs | None = None,
    ) -> RenderPageV1 | None:
        """Load a RenderPageV1 from the artifact store.

        S5U-1229 — reuse *render_cache* on hit (``in`` honors a cached ``None``).
        S5U-1264 — a miss resolves through the run-bound selection (``page_refs``,
        with edition-aware mtime fallback in ``load_run_bound_render``).
        """
        if render_cache is not None and page_id in render_cache:
            data = render_cache[page_id]
        else:
            data = load_run_bound_render(
                ctx.artifact_store,
                page_refs=page_refs or {},
                document_id=ctx.document_id,
                page_id=page_id,
                edition=edition,
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
