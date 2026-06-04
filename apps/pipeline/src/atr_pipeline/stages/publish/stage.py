"""Publish stage — build a release bundle from pipeline artifacts."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.stages.publish.bundle_builder import (
    BundleRefs,
    build_release_bundle,
    flatten_raster_refs,
)
from atr_pipeline.stages.publish.qa_gate import QAGateResult, evaluate_qa_gate
from atr_schemas.enums import StageScope
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.qa_summary_v1 import QASummaryV1


class PublishResult(BaseModel):
    """Summary of the publish stage output."""

    document_id: str
    build_id: str = ""
    files_published: int = Field(default=0, ge=0)
    output_dir: str = ""
    # S5U-870 — QA-gate disposition stamped into the stage artifact so reviewers
    # and the web side can see whether this bundle was a review-only draft built
    # over blocking QA. ``review_only`` is True only when the explicit escape
    # hatch was used; ``blocking`` reflects ``QASummaryV1.blocking`` for the run.
    review_only: bool = False
    blocking: bool = False


class PublishStage:
    """Build a release bundle from the current run's artifacts.

    Uses explicit artifact refs from the run's stage events — no
    directory enumeration.
    """

    @property
    def name(self) -> str:
        return "publish"

    @property
    def scope(self) -> StageScope:
        return StageScope.DOCUMENT

    @property
    def version(self) -> str:
        # 1.0 -> 1.1 (S5U-870): the stage now enforces the blocking-QA release
        # gate before building the bundle and the PublishResult artifact gained
        # ``review_only`` / ``blocking`` fields. The bump invalidates cached
        # publish events from v1.0 so a previously-cached "publish succeeded" on
        # a blocking run cannot be served from cache without re-evaluating the
        # gate (the S5U-662 stale-cache failure mode). A refusal raises before
        # any artifact write, so the blocking case is never cached at all.
        return "1.1"

    def extra_cache_inputs(self, ctx: StageContext) -> list[str]:
        """Fold the run's QA-gate state into the publish cache key (S5U-870).

        The blocking-QA gate runs inside :meth:`run`, but the executor checks
        the cache *before* calling ``run`` — so a publish event cached while the
        run was non-blocking could otherwise be served from cache after the run
        becomes blocking, silently bypassing the gate (an S5U-662-class hazard
        for a runtime-state-dependent gate). Folding the QA summary's blocking
        flag and the explicit ``publish_review_only`` flag into the cache key
        means any gate-relevant state change invalidates the cached event, so
        the gate always re-evaluates. The config-driven ``block_publish_on`` is
        already part of the config hash.
        """
        summary = _load_qa_summary_from_registry(ctx)
        blocking = "none" if summary is None else str(summary.blocking)
        return [
            f"qa_blocking:{blocking}",
            f"review_only:{ctx.publish_review_only}",
        ]

    def run(self, ctx: StageContext, input_data: BaseModel | None) -> PublishResult:
        gate_result = self._enforce_qa_gate(ctx)

        render_data = _load_render_result_from_registry(ctx)
        page_refs = render_data.get("page_refs", {})
        if not isinstance(page_refs, dict) or not page_refs:
            msg = "No render page refs found. Run the render stage first."
            raise RuntimeError(msg)

        companion_refs = {
            k: str(render_data[k])
            for k in ("glossary_ref", "search_docs_ref", "nav_ref")
            if render_data.get(k)
        }

        raw_image_refs = render_data.get("image_refs", {})
        image_refs = (
            {str(k): str(v) for k, v in raw_image_refs.items()}
            if isinstance(raw_image_refs, dict)
            else {}
        )

        flat_rasters = flatten_raster_refs(render_data.get("raster_refs", {}))

        output_dir = ctx.artifact_store.root / ctx.document_id / "release"

        run_row = get_run(ctx.registry_conn, ctx.run_id)
        source_sha = run_row["source_pdf_sha256"] if run_row else ""

        manifest = build_release_bundle(
            document_id=ctx.document_id,
            artifact_root=ctx.artifact_store.root,
            output_dir=output_dir,
            pipeline_version=ctx.config.pipeline.version,
            refs=BundleRefs(
                render_pages={str(k): str(v) for k, v in page_refs.items()},
                companions=companion_refs,
                images=image_refs,
                rasters=flat_rasters,
                run_id=ctx.run_id,
                source_pdf_sha256=source_sha or "",
                edition="en" if ctx.edition == "en" else "ru",
            ),
        )

        if gate_result.is_draft:
            ctx.logger.warning(
                "REVIEW-ONLY DRAFT: published %d files to %s over BLOCKING QA "
                "(codes=%s, pages=%s). This bundle MUST NOT be released as-is.",
                len(manifest.files),
                output_dir,
                gate_result.blocking_codes,
                gate_result.blocking_pages,
            )
        else:
            ctx.logger.info("Published %d files to %s", len(manifest.files), output_dir)

        return PublishResult(
            document_id=ctx.document_id,
            build_id=manifest.build_id,
            files_published=len(manifest.files),
            output_dir=str(output_dir),
            review_only=gate_result.review_only,
            blocking=gate_result.blocking,
        )

    @staticmethod
    def _enforce_qa_gate(ctx: StageContext) -> QAGateResult:
        """Run the blocking-QA release gate for the current run.

        Resolves the run's QA summary + records from its stage events (mirroring
        ``_load_render_result_from_registry`` — never a cross-run mtime pick) and
        delegates to the shared gate. Raises ``QAGateError`` (refusing the
        publish) unless ``ctx.publish_review_only`` was explicitly set, in which
        case a blocking run proceeds as a loudly-labeled draft.
        """
        block_on = set(ctx.config.qa.block_publish_on)
        summary = _load_qa_summary_from_registry(ctx)
        records = _load_qa_records(ctx, summary) if summary else []
        return evaluate_qa_gate(
            context="Publish",
            summary=summary,
            records=records,
            block_on=block_on,
            review_only=ctx.publish_review_only,
            run_id=ctx.run_id,
        )


def _load_render_result_from_registry(ctx: StageContext) -> dict[str, object]:
    """Load the render stage artifact using the current run's stage events."""
    events = list_stage_events(ctx.registry_conn, run_id=ctx.run_id)
    render_event = next(
        (
            ev
            for ev in events
            if ev["stage_name"] == "render" and ev["status"] in ("completed", "cached")
        ),
        None,
    )
    if render_event is None or not render_event["artifact_ref"]:
        msg = "No render result found. Run the render stage first."
        raise RuntimeError(msg)

    artifact_path = ctx.artifact_store.root / render_event["artifact_ref"]
    return json.loads(artifact_path.read_text())  # type: ignore[no-any-return]


def _load_qa_summary_from_registry(ctx: StageContext) -> QASummaryV1 | None:
    """Load the current run's QA summary via its QA stage event.

    Ref-bound to ``ctx.run_id`` (mirrors ``_load_render_result_from_registry``);
    never an mtime pick across runs. Returns ``None`` only when the run has no
    QA stage event at all — the shared gate treats that as a fail-closed refusal
    (a publish/export cannot proceed without a verifiable QA summary). A QA event
    that exists but whose artifact is missing/unreadable on disk also returns
    ``None`` (degraded to the same fail-closed refusal) after logging.
    """
    events = list_stage_events(ctx.registry_conn, run_id=ctx.run_id)
    # Pick the LATEST qa event for the run (events come back event_id-ascending),
    # mirroring ``_export_run._qa_summary_ref_for_run``'s ``ORDER BY event_id
    # DESC LIMIT 1`` — a re-run of QA within the same run supersedes the earlier
    # summary; the gate must evaluate the most recent QA state.
    qa_event = next(
        (
            ev
            for ev in reversed(events)
            if ev["stage_name"] == "qa" and ev["status"] in ("completed", "cached")
        ),
        None,
    )
    if qa_event is None or not qa_event["artifact_ref"]:
        return None

    artifact_path = ctx.artifact_store.root / qa_event["artifact_ref"]
    try:
        data = json.loads(artifact_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        ctx.logger.error(
            "QA summary artifact %s for run %s is unreadable: %s",
            qa_event["artifact_ref"],
            ctx.run_id,
            exc,
        )
        return None
    return QASummaryV1.model_validate(data)


def _load_qa_records(ctx: StageContext, summary: QASummaryV1) -> list[QARecordV1]:
    """Load the QA records referenced by *summary* (for naming blocking codes).

    Missing/unreadable record artifacts are skipped with a warning — the gate
    still refuses on a blocking summary even when records cannot be named
    (it degrades the refusal message, never the refusal itself).
    """
    records: list[QARecordV1] = []
    for ref in summary.record_refs:
        path = ctx.artifact_store.root / ref
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            ctx.logger.warning("QA record %s for run %s unreadable: %s", ref, ctx.run_id, exc)
            continue
        records.append(QARecordV1.model_validate(data))
    return records
