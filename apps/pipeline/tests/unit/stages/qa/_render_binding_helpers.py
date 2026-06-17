"""Shared test helper: make out-of-band render seeds part of the run (S5U-1264).

Many QA stage tests run the real ``RenderStage`` to populate a store, then seed
or overwrite a page's ``render_page.v1`` artifact *out of band* (a direct
``put_json``) to inject a rule-triggering render. Before S5U-1264 QA selected
each render by newest-by-mtime, so an out-of-band seed (newest write) was picked
up automatically.

S5U-1264 binds QA's per-page render selection to the current run's
``RenderResult.page_refs`` (recorded as the render stage event's ``artifact_ref``).
An out-of-band seed for a page the render stage already covered is therefore
*ignored* — exactly the cross-run-splice protection the issue adds. For test
seeds that are meant to represent "the render this run produced for this page",
this helper re-records the run's render stage event so its ``page_refs`` point at
the seeded artifacts, making the seed a genuine part of the run's render output.

Use after seeding renders out of band, before invoking the QA stage.
"""

from __future__ import annotations

import json

from atr_pipeline.registry.events import (
    list_stage_events,
    record_stage_finish,
    record_stage_start,
)
from atr_pipeline.runner.stage_context import StageContext
from atr_pipeline.store.artifact_store import ArtifactStore


def _latest_render_ref(store: ArtifactStore, document_id: str, page_id: str) -> str | None:
    path = store.resolve_latest_path(
        document_id=document_id,
        schema_family="render_page.v1",
        scope="page",
        entity_id=page_id,
    )
    if path is None:
        return None
    return str(path.relative_to(store.root))


def rebind_run_render(ctx: StageContext, page_ids: list[str]) -> None:
    """Re-record the run's render stage event so its ``page_refs`` cover *page_ids*.

    Reads the run's existing render result (if any), updates / inserts a ref for
    each page in *page_ids* (resolving each page's latest render artifact on
    disk), writes the merged render result as a fresh ``render`` artifact, and
    records a new completed render stage event pointing at it. ``resolve_run_page_refs``
    then returns the merged index, so QA's run-bound selection picks the seeds.
    """
    store = ctx.artifact_store
    events = list_stage_events(ctx.registry_conn, run_id=ctx.run_id)
    render_result: dict[str, object] = {"document_id": ctx.document_id, "pages_rendered": 0}
    for ev in reversed(events):
        if ev["stage_name"] == "render" and ev["status"] in ("completed", "cached"):
            ref = ev["artifact_ref"]
            if ref:
                existing = json.loads((store.root / ref).read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    render_result = existing
            break

    raw_refs = render_result.get("page_refs", {})
    page_refs: dict[str, str] = (
        {str(k): str(v) for k, v in raw_refs.items()} if isinstance(raw_refs, dict) else {}
    )
    for pid in page_ids:
        ref = _latest_render_ref(store, ctx.document_id, pid)
        if ref is not None:
            page_refs[pid] = ref
    render_result["page_refs"] = page_refs
    render_result["pages_rendered"] = len(page_refs)

    new_ref = store.put_json(
        document_id=ctx.document_id,
        schema_family="render",
        scope="document",
        entity_id=ctx.document_id,
        data=render_result,
    )
    event_id = record_stage_start(
        ctx.registry_conn,
        run_id=ctx.run_id,
        stage_name="render",
        scope="document",
        entity_id=ctx.document_id,
        cache_key="test-rebind-render",
    )
    record_stage_finish(
        ctx.registry_conn,
        event_id=event_id,
        status="completed",
        artifact_ref=new_ref.relative_path,
        duration_ms=0,
    )
