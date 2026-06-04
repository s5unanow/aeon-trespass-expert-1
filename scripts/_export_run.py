"""Ref-bound run resolution for the web export (S5U-869).

``make export`` historically selected each pipeline artifact independently
by mtime (``export_to_web._pick_latest``), so a single export could splice a
render page from run A with the QA summary / glossary / images from run B —
the exported bundle was never guaranteed to be internally consistent with one
real pipeline run.

This module resolves a *single* run from ``var/registry.db`` and exposes every
artifact ref of that run (render result, QA summary, glossary, navigation,
images, rasters) so the exporter binds the whole bundle to one run — mirroring
the already-ref-bound ``PublishStage._load_render_result_from_registry`` on the
``atr release`` path. ``PublishStage`` itself is untouched.

Fail-closed contract (`.claude/rules/guards.md` Rule G1): every degenerate
input — missing/unreadable/empty registry, non-existent or unfinished run,
missing required artifact — raises :class:`RunResolutionError`. The exporter
turns that into a non-zero exit. There is **no** silent mtime fall-back to a
different run's artifact.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RunResolutionError(Exception):
    """A required run / artifact could not be resolved — fail closed.

    Raised for every G1 degenerate input so the exporter exits non-zero with a
    clear message instead of writing a partial or cross-run-spliced bundle.
    """


class ResolvedRun(BaseModel):
    """All artifact refs + provenance bound to a single pipeline run."""

    run_id: str
    document_id: str
    git_commit: str = ""
    edition: str = "all"
    source_pdf_sha256: str = ""
    status: str = ""
    # Render result manifest payload — the run's self-contained artifact index
    # (page_refs / image_refs / raster_refs / glossary_ref / nav_ref / ...).
    render_result: dict[str, object] = Field(default_factory=dict)
    # Relative ref (under the artifact root) of the run's QA summary, if any.
    qa_summary_ref: str = ""

    @property
    def page_refs(self) -> dict[str, str]:
        raw = self.render_result.get("page_refs", {})
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def image_refs(self) -> dict[str, str]:
        raw = self.render_result.get("image_refs", {})
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    @property
    def glossary_ref(self) -> str:
        ref = self.render_result.get("glossary_ref", "")
        return str(ref) if ref else ""

    def provenance(self) -> dict[str, str]:
        """Provenance block stamped into the exported edition manifest."""
        return {
            "run_id": self.run_id,
            "git_commit": self.git_commit,
            "edition": self.edition,
            "source_pdf_sha256": self.source_pdf_sha256,
        }


def _open_registry_readonly(registry_path: Path) -> sqlite3.Connection:
    """Open the registry for read-only querying, failing closed on any error.

    G1: a missing or unreadable/corrupt DB is a broken release input, not
    "nothing to export". Both raise :class:`RunResolutionError`.
    """
    if not registry_path.exists():
        msg = (
            f"Registry DB not found at {registry_path}. Run the pipeline "
            f"(`atr run --doc <id>`) before exporting; refusing to export."
        )
        raise RunResolutionError(msg)
    try:
        conn = sqlite3.connect(f"file:{registry_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Touch the runs table so a corrupt / schema-less DB fails here.
        conn.execute("SELECT COUNT(*) FROM runs").fetchone()
    except sqlite3.Error as exc:
        logger.error("Registry DB unreadable at %s: %s", registry_path, exc)
        msg = f"Registry DB at {registry_path} is unreadable or corrupt: {exc}"
        raise RunResolutionError(msg) from exc
    return conn


def _latest_complete_run(
    conn: sqlite3.Connection, document_id: str, edition: str | None
) -> sqlite3.Row | None:
    """Newest complete run for *document_id*, optionally scoped to *edition*.

    A run whose own ``edition`` is ``"all"`` (full EN+RU pipeline) satisfies any
    requested edition; an ``"en"``/``"ru"`` run satisfies only its own edition.
    ``edition=None`` matches any edition.
    """
    if edition is None:
        cursor = conn.execute(
            "SELECT * FROM runs WHERE document_id = ? AND status = 'completed'"
            " AND finished_at IS NOT NULL ORDER BY started_at DESC LIMIT 1",
            (document_id,),
        )
    else:
        cursor = conn.execute(
            "SELECT * FROM runs WHERE document_id = ? AND status = 'completed'"
            " AND finished_at IS NOT NULL AND edition IN (?, 'all')"
            " ORDER BY started_at DESC LIMIT 1",
            (document_id, edition),
        )
    return cast("sqlite3.Row | None", cursor.fetchone())


def _resolve_run_row(
    conn: sqlite3.Connection,
    document_id: str,
    run_id: str | None,
    edition: str | None,
) -> sqlite3.Row:
    """Resolve the target run row, failing closed on every degenerate case."""
    if run_id:
        cursor = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row is None:
            msg = f"--run-id {run_id!r} not found in registry; refusing to export."
            raise RunResolutionError(msg)
        if row["document_id"] != document_id:
            msg = (
                f"--run-id {run_id!r} belongs to document {row['document_id']!r}, "
                f"not {document_id!r}; refusing to export."
            )
            raise RunResolutionError(msg)
        if row["status"] != "completed" or row["finished_at"] is None:
            msg = (
                f"--run-id {run_id!r} is not complete "
                f"(status={row['status']!r}, finished_at={row['finished_at']!r}); "
                f"refusing to export a partial bundle."
            )
            raise RunResolutionError(msg)
        # An explicit --run-id must not be exported into a mismatched edition
        # bundle (e.g. an EN run forced into the ru/ directory under
        # --edition all). A run whose own edition is 'all' satisfies any
        # request; otherwise the requested edition must equal the run's.
        run_edition = row["edition"] or "all"
        if edition is not None and run_edition not in (edition, "all"):
            msg = (
                f"--run-id {run_id!r} is an {run_edition!r}-edition run but a "
                f"{edition!r} export was requested; refusing to splice a run "
                f"across editions. Export {run_edition!r} explicitly "
                f"(--edition {run_edition})."
            )
            raise RunResolutionError(msg)
        return cast("sqlite3.Row", row)

    row = _latest_complete_run(conn, document_id, edition)
    if row is None:
        scope = f"document {document_id!r}"
        if edition is not None:
            scope += f" edition {edition!r}"
        msg = (
            f"No complete runs for {scope} in the registry. Run the pipeline "
            f"to completion before exporting; refusing to export."
        )
        raise RunResolutionError(msg)
    return row


def _render_result_for_run(
    conn: sqlite3.Connection, run_id: str, artifact_root: Path
) -> dict[str, object]:
    """Load the render result artifact bound to *run_id* via its stage event.

    Mirrors ``PublishStage._load_render_result_from_registry``: select the
    run's render stage event (completed or cached), resolve its artifact_ref
    against the artifact root. Fail closed if absent or missing on disk.
    """
    cursor = conn.execute(
        "SELECT artifact_ref FROM stage_events WHERE run_id = ?"
        " AND stage_name = 'render' AND status IN ('completed', 'cached')"
        " AND artifact_ref IS NOT NULL ORDER BY event_id DESC LIMIT 1",
        (run_id,),
    )
    row = cursor.fetchone()
    if row is None or not row["artifact_ref"]:
        msg = f"Run {run_id!r} has no render artifact; refusing to export."
        raise RunResolutionError(msg)

    ref = str(row["artifact_ref"])
    path = artifact_root / ref
    if not path.is_file():
        msg = f"Render artifact {ref!r} for run {run_id!r} is missing on disk; refusing to export."
        raise RunResolutionError(msg)
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Render artifact %s for run %s unreadable: %s", ref, run_id, exc)
        msg = f"Render artifact {ref!r} for run {run_id!r} is unreadable: {exc}"
        raise RunResolutionError(msg) from exc
    if not isinstance(data, dict):
        msg = f"Render artifact {ref!r} for run {run_id!r} is not an object; refusing to export."
        raise RunResolutionError(msg)
    return data


def _qa_summary_ref_for_run(conn: sqlite3.Connection, run_row: sqlite3.Row) -> str:
    """Resolve the run's QA summary ref (runs.qa_summary_ref, then stage event)."""
    ref = run_row["qa_summary_ref"]
    if ref:
        return str(ref)
    cursor = conn.execute(
        "SELECT artifact_ref FROM stage_events WHERE run_id = ?"
        " AND stage_name = 'qa' AND status IN ('completed', 'cached')"
        " AND artifact_ref IS NOT NULL ORDER BY event_id DESC LIMIT 1",
        (run_row["run_id"],),
    )
    row = cursor.fetchone()
    return str(row["artifact_ref"]) if row and row["artifact_ref"] else ""


def resolve_run(
    registry_path: Path,
    document_id: str,
    *,
    artifact_root: Path,
    run_id: str | None = None,
    edition: str | None = None,
) -> ResolvedRun:
    """Resolve a single run and all its artifact refs, failing closed.

    ``run_id=None`` selects the latest *complete* run for ``document_id``
    (scoped to ``edition`` when given — an ``edition="all"`` run satisfies any
    request). Every degenerate input raises :class:`RunResolutionError`.
    """
    conn = _open_registry_readonly(registry_path)
    try:
        run_row = _resolve_run_row(conn, document_id, run_id, edition)
        rid = str(run_row["run_id"])
        render_result = _render_result_for_run(conn, rid, artifact_root)
        qa_ref = _qa_summary_ref_for_run(conn, run_row)
        resolved = ResolvedRun(
            run_id=rid,
            document_id=document_id,
            git_commit=str(run_row["git_commit"] or ""),
            edition=str(run_row["edition"] or "all"),
            source_pdf_sha256=str(run_row["source_pdf_sha256"] or ""),
            status=str(run_row["status"]),
            render_result=render_result,
            qa_summary_ref=qa_ref,
        )
    finally:
        conn.close()
    logger.info(
        "Resolved run %s (edition=%s, git=%s, %d page refs)",
        resolved.run_id,
        resolved.edition,
        resolved.git_commit[:8] or "-",
        len(resolved.page_refs),
    )
    return resolved


def load_run_pages(resolved: ResolvedRun, artifact_root: Path) -> dict[str, dict[str, object]]:
    """Load every render-page payload bound to *resolved* by ref.

    Fail-closed (guards.md G1): a ``page_refs`` entry whose artifact is missing
    on disk is a broken release input, not "skip the page" — refuse rather than
    silently exporting an incomplete bundle.
    """
    pages: dict[str, dict[str, object]] = {}
    for pid, ref in resolved.page_refs.items():
        path = artifact_root / ref
        if not path.is_file():
            msg = (
                f"Run {resolved.run_id!r} page {pid!r} artifact {ref!r} is missing "
                f"on disk; refusing to export an incomplete bundle."
            )
            raise RunResolutionError(msg)
        pages[pid] = json.loads(path.read_text())
    return pages


def resolve_glossary_path(resolved: ResolvedRun, artifact_root: Path) -> Path | None:
    """Resolve the run's glossary artifact path, refusing on a missing ref file.

    Returns ``None`` only when the run carries no glossary ref at all. When the
    ref is set the file must exist — never mtime-fall-back to a stray glossary.
    """
    ref = resolved.glossary_ref
    if not ref:
        return None
    path = artifact_root / ref
    if not path.is_file():
        msg = (
            f"Run {resolved.run_id!r} glossary artifact {ref!r} is missing on disk; "
            f"refusing to export (no mtime fall-back to another run's glossary)."
        )
        raise RunResolutionError(msg)
    return path


def resolve_qa_summary_path(resolved: ResolvedRun, artifact_root: Path) -> Path | None:
    """Resolve the run's QA summary artifact path, refusing on a missing ref file."""
    ref = resolved.qa_summary_ref
    if not ref:
        return None
    path = artifact_root / ref
    if not path.is_file():
        msg = (
            f"Run {resolved.run_id!r} QA summary artifact {ref!r} is missing on disk; "
            f"refusing to export (no mtime fall-back to another run's QA summary)."
        )
        raise RunResolutionError(msg)
    return path
