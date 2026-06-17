"""Run-id-bound per-page render selection for the QA stage (S5U-1264).

The intra-pipeline read path historically selected per-page ``render_page.v1``
artifacts by **mtime** (``store.edition_selection.load_latest_json_for_edition``
→ ``ArtifactStore.latest_sort_key``). On a partial / concurrent / copied store
where mtimes are unreliable (``os.utime`` on content reuse, ``cp -p``, coarse FS
granularity), the "latest" per-page render is whatever has the newest mtime /
lex-max content hash — **not necessarily the render the current run produced**.
The export path is already hardened against this class (S5U-869 ``resolve_run`` /
``ResolvedRun``); intra-pipeline QA reads were not (deferred from S5U-1229).

This module is the intra-pipeline analog of the export path's run-id binding.
It reuses the index that **already exists**: ``RenderStage.run`` returns a
``RenderResult`` whose ``page_refs`` maps ``page_id -> relative render_page.v1
ref``, and the executor records that ``RenderResult`` as the render stage's
document-scope ``artifact_ref`` in ``stage_events`` — already bound to
``ctx.run_id``. ``PublishStage._load_render_result_from_registry`` is the
existing in-pipeline precedent that resolves the same index by run id; this
module mirrors it for the QA read path. **No new artifact is written** — the
resolver is a pure read over existing stage events + existing render artifacts.

Fail-SAFE (not fail-CLOSED) contract — a deliberate, reviewer-visible divergence
from ``.claude/rules/guards.md`` Rule G1: when the run's render event / artifact
is absent or unreadable, or a specific page is not covered by ``page_refs``, the
resolver degrades to the pre-S5U-1264 mtime selection (with a WARNING) rather
than refusing. QA is an **advisory in-pipeline stage** that must remain runnable
on a legacy / partial store; the export path (``scripts/_export_run.py``) remains
the fail-closed release gate. Losing the run-binding guarantee for an uncovered
page is strictly better than making QA un-runnable; the binding is enforced for
every page the current run's render result actually covers.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_pipeline.store.edition_selection import load_latest_json_for_edition

RenderPageRefs = dict[str, str]


def resolve_run_page_refs(ctx: StageContext) -> RenderPageRefs:
    """Return ``{page_id: relative render_page.v1 ref}`` bound to ``ctx.run_id``.

    Resolves the current run's latest completed/cached ``render`` stage event,
    loads its ``RenderResult`` artifact, and returns its ``page_refs``. Returns
    an empty dict (the caller then falls back to mtime selection per page) when:

    * the run has no completed/cached render event yet, or
    * the render event carries no ``artifact_ref``, or
    * the render artifact is missing on disk, unreadable, or not a JSON object,
      or carries no usable ``page_refs``.

    Each of those is logged at WARNING with context — never a bare ``except``.
    """
    render_ref = _latest_render_artifact_ref(ctx)
    if render_ref is None:
        ctx.logger.warning(
            "S5U-1264: run %s has no render stage event; QA render selection "
            "falls back to mtime (no run-binding guarantee)",
            ctx.run_id,
        )
        return {}

    artifact_path = ctx.artifact_store.root / render_ref
    if not artifact_path.is_file():
        ctx.logger.warning(
            "S5U-1264: render result %s for run %s missing on disk; QA render "
            "selection falls back to mtime",
            render_ref,
            ctx.run_id,
        )
        return {}

    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        ctx.logger.warning(
            "S5U-1264: render result %s for run %s unreadable (%s); QA render "
            "selection falls back to mtime",
            render_ref,
            ctx.run_id,
            exc,
        )
        return {}

    if not isinstance(data, dict):
        ctx.logger.warning(
            "S5U-1264: render result %s for run %s is not a JSON object; QA "
            "render selection falls back to mtime",
            render_ref,
            ctx.run_id,
        )
        return {}

    raw_refs = data.get("page_refs", {})
    if not isinstance(raw_refs, dict) or not raw_refs:
        ctx.logger.warning(
            "S5U-1264: render result %s for run %s has no page_refs; QA render "
            "selection falls back to mtime",
            render_ref,
            ctx.run_id,
        )
        return {}

    return {str(k): str(v) for k, v in raw_refs.items()}


def _latest_render_artifact_ref(ctx: StageContext) -> str | None:
    """Relative ref of the run's latest completed/cached render artifact, or None.

    Mirrors ``PublishStage._load_render_result_from_registry``'s selection but
    picks the LATEST such event (events come back event_id-ascending; a re-run
    of render within the same run supersedes an earlier one), matching
    ``_export_run._render_result_for_run``'s ``ORDER BY event_id DESC`` intent.
    """
    events = list_stage_events(ctx.registry_conn, run_id=ctx.run_id)
    for ev in reversed(events):
        if ev["stage_name"] == "render" and ev["status"] in ("completed", "cached"):
            ref = ev["artifact_ref"]
            return str(ref) if ref else None
    return None


def load_run_bound_render(
    store: ArtifactStore,
    *,
    page_refs: RenderPageRefs,
    document_id: str,
    page_id: str,
    edition: str,
) -> dict[str, Any] | None:
    """Load a page's ``render_page.v1`` payload, preferring the run-bound ref.

    Resolution order:

    1. If *page_refs* covers *page_id* and that exact artifact is on disk and
       parses, return it — the run-bound selection (no mtime).
    2. Otherwise (page not covered, ref file gone, or unreadable) fall back to
       the edition-aware mtime selection ``load_latest_json_for_edition`` so QA
       still evaluates *something* for the page. A covered-but-broken ref logs a
       WARNING; an uncovered page falls back silently (the run simply did not
       render it, which is normal for ``--pages`` subsets and legacy stores).

    Returns ``None`` only when neither the run-bound ref nor the mtime fallback
    yields an artifact (page genuinely has no render for the edition).
    """
    ref = page_refs.get(page_id)
    if ref:
        path = store.root / ref
        if path.is_file():
            try:
                data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logging.getLogger(__name__).warning(
                    "S5U-1264: run-bound render %s for page %s unreadable (%s); "
                    "falling back to mtime selection",
                    ref,
                    page_id,
                    exc,
                )
            else:
                return data
        else:
            logging.getLogger(__name__).warning(
                "S5U-1264: run-bound render ref %s for page %s missing on disk; "
                "falling back to mtime selection",
                ref,
                page_id,
            )

    return load_latest_json_for_edition(
        store,
        document_id=document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
        edition=edition,
    )
