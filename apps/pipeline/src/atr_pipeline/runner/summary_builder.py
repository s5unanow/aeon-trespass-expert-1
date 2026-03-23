"""Build a RunSummaryV1 from registry data after a pipeline run."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from atr_pipeline.registry.events import list_stage_events
from atr_pipeline.registry.runs import get_run
from atr_schemas.run_summary_v1 import RunSummaryV1


def build_run_summary(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    document_id: str,
    stages_requested: list[str],
    page_filter: frozenset[str] | None = None,
) -> RunSummaryV1:
    """Assemble a RunSummaryV1 from the runs table and stage_events."""
    run = get_run(conn, run_id)
    if run is None:
        msg = f"Run not found: {run_id}"
        raise ValueError(msg)

    events = list_stage_events(conn, run_id=run_id)

    # Compute stage-level aggregates
    stage_statuses: dict[str, str] = {}
    for ev in events:
        if ev["scope"] == "document":
            stage_statuses[ev["stage_name"]] = ev["status"]

    stages_completed = sum(1 for s in stage_statuses.values() if s == "completed")
    stages_failed = sum(1 for s in stage_statuses.values() if s == "failed")

    # Compute page-level aggregates from page-scoped events (per unique page)
    page_events = [ev for ev in events if ev["scope"] == "page"]
    page_ids: set[str] = set()
    cached_pages: set[str] = set()
    failed_pages: set[str] = set()
    for ev in page_events:
        page_ids.add(ev["entity_id"])
        if ev["status"] == "cached":
            cached_pages.add(ev["entity_id"])
        elif ev["status"] == "failed":
            failed_pages.add(ev["entity_id"])
    pages_processed = len(page_ids) - len(failed_pages)

    # Compute duration
    duration_s = _compute_duration(run["started_at"], run["finished_at"])

    return RunSummaryV1(
        run_id=run_id,
        document_id=document_id,
        status=run["status"],
        edition=run["edition"] or "all",
        pipeline_version=run["pipeline_version"],
        git_commit=run["git_commit"] or "",
        stages_requested=stages_requested,
        stages_completed=stages_completed,
        stages_failed=stages_failed,
        pages_total=len(page_ids),
        pages_processed=pages_processed,
        pages_cached=len(cached_pages),
        pages_failed=len(failed_pages),
        page_filter=sorted(page_filter) if page_filter else None,
        duration_s=duration_s,
        started_at=run["started_at"],
        finished_at=run["finished_at"] or "",
        config_hash=run["config_hash"],
        source_pdf_sha256=run["source_pdf_sha256"] or "",
    )


def _compute_duration(started_at: str, finished_at: str | None) -> float:
    """Compute run duration in seconds from ISO timestamps."""
    if not finished_at:
        return 0.0
    try:
        start = datetime.fromisoformat(started_at).replace(tzinfo=UTC)
        end = datetime.fromisoformat(finished_at).replace(tzinfo=UTC)
        return round((end - start).total_seconds(), 1)
    except (ValueError, TypeError):
        return 0.0
