"""Read-only source readers for ``scripts/analytics_snapshot.py``.

Each reader pulls one scattered signal (registry runs, QA metrics, code
erosion, agent-throughput logs) and returns a typed Pydantic section. The
best-effort git/gh network signals live in ``_analytics_network``. Readers
are *pure read-only*: they open files / the registry in read-only mode and
never mutate the registry or any artifact.

Fail-closed contract (adapted from ``.claude/rules/guards.md`` G1 for a
read-only aggregator):

* registry unreadable / schema mismatch -> the run-health section is marked
  ``available=False`` with an ``error`` string. The caller (snapshot.py)
  treats a degraded run-health section as a non-zero exit signal so a degraded
  snapshot never masquerades as healthy.
* qa_metrics malformed -> the QA section surfaces the parse error in
  ``error`` and is marked ``available=False``; QA health is never silently
  dropped (the caller fails non-zero on it too).
* git / gh subprocess failure -> only *that* field is marked unavailable;
  the rest of the snapshot still renders.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger("atr.analytics_snapshot")

# Columns the run-health reader depends on. A registry missing any of these is
# a schema mismatch -> fail-closed (degraded), not a silent empty success.
_REQUIRED_RUN_COLUMNS = frozenset({"run_id", "document_id", "status", "started_at", "finished_at"})
_REQUIRED_EVENT_COLUMNS = frozenset({"run_id", "stage_name", "status", "duration_ms"})


# --------------------------------------------------------------------------- #
# Run health (var/registry.db: runs + stage_events)
# --------------------------------------------------------------------------- #
class StageDuration(BaseModel):
    stage_name: str
    runs: int
    avg_duration_ms: float
    max_duration_ms: int


class RunRecord(BaseModel):
    run_id: str
    document_id: str
    status: str
    started_at: str
    finished_at: str | None = None


class RunHealth(BaseModel):
    available: bool
    error: str | None = None
    total_runs: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    recent_runs: list[RunRecord] = Field(default_factory=list)
    stage_durations: list[StageDuration] = Field(default_factory=list)


def _degraded_run_health(error: str) -> RunHealth:
    logger.warning("run-health degraded: %s", error)
    return RunHealth(available=False, error=error)


def read_run_health(registry_path: Path, *, recent_limit: int = 10) -> RunHealth:
    """Aggregate run + stage-event health from the registry (read-only).

    Opens with ``mode=ro`` so the reader can never mutate the registry. A
    missing file, an unreadable DB, or a schema mismatch yields a degraded
    (``available=False``) section rather than a silent empty-but-healthy one.
    """
    if not registry_path.is_file():
        return _degraded_run_health(f"registry not found at {registry_path}")
    uri = f"file:{registry_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return _degraded_run_health(f"cannot open registry: {exc}")
    conn.row_factory = sqlite3.Row
    try:
        return _query_run_health(conn, recent_limit=recent_limit)
    except sqlite3.Error as exc:
        return _degraded_run_health(f"registry query failed: {exc}")
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _query_run_health(conn: sqlite3.Connection, *, recent_limit: int) -> RunHealth:
    run_cols = _table_columns(conn, "runs")
    event_cols = _table_columns(conn, "stage_events")
    if not run_cols:
        return _degraded_run_health("registry has no 'runs' table (schema mismatch)")
    missing_runs = _REQUIRED_RUN_COLUMNS - run_cols
    if missing_runs:
        cols = ", ".join(sorted(missing_runs))
        return _degraded_run_health(f"runs table missing columns: {cols}")
    missing_events = _REQUIRED_EVENT_COLUMNS - event_cols
    if event_cols and missing_events:
        cols = ", ".join(sorted(missing_events))
        return _degraded_run_health(f"stage_events table missing columns: {cols}")

    total = int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
    status_rows = conn.execute("SELECT status, COUNT(*) AS n FROM runs GROUP BY status").fetchall()
    status_counts = {str(r["status"]): int(r["n"]) for r in status_rows}

    recent_rows = conn.execute(
        "SELECT run_id, document_id, status, started_at, finished_at "
        "FROM runs ORDER BY started_at DESC LIMIT ?",
        (recent_limit,),
    ).fetchall()
    recent = [
        RunRecord(
            run_id=str(r["run_id"]),
            document_id=str(r["document_id"]),
            status=str(r["status"]),
            started_at=str(r["started_at"]),
            finished_at=str(r["finished_at"]) if r["finished_at"] is not None else None,
        )
        for r in recent_rows
    ]

    durations: list[StageDuration] = []
    if event_cols:
        dur_rows = conn.execute(
            "SELECT stage_name, COUNT(*) AS n, "
            "AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms "
            "FROM stage_events WHERE duration_ms IS NOT NULL "
            "GROUP BY stage_name ORDER BY avg_ms DESC"
        ).fetchall()
        durations = [
            StageDuration(
                stage_name=str(r["stage_name"]),
                runs=int(r["n"]),
                avg_duration_ms=round(float(r["avg_ms"]), 1),
                max_duration_ms=int(r["max_ms"]),
            )
            for r in dur_rows
        ]

    return RunHealth(
        available=True,
        total_runs=total,
        status_counts=status_counts,
        recent_runs=recent,
        stage_durations=durations,
    )


# --------------------------------------------------------------------------- #
# QA health (latest qa_metrics.json)
# --------------------------------------------------------------------------- #
class QAHealth(BaseModel):
    available: bool
    error: str | None = None
    source: str | None = None
    document_id: str | None = None
    edition: str | None = None
    pages_total: int = 0
    clean_page_rate: float = 0.0
    blocking_count: int = 0
    waived_count: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    findings_by_layer: dict[str, int] = Field(default_factory=dict)
    findings_by_code_top10: list[dict[str, int]] = Field(default_factory=list)


def find_latest_qa_metrics(artifact_root: Path, document_id: str) -> Path | None:
    """Locate the newest qa_metrics.v1 artifact for *document_id* by mtime.

    Mirrors the artifact layout used by the QA stage / ``_export_qa.py``:
    ``<artifact_root>/<doc>/qa_metrics.v1/document/<doc>/<hash>.json``.
    """
    metrics_dir = artifact_root / document_id / "qa_metrics.v1" / "document" / document_id
    if not metrics_dir.is_dir():
        return None
    candidates = sorted(metrics_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def read_qa_health(metrics_path: Path | None) -> QAHealth:
    """Parse a qa_metrics.json. A malformed file surfaces the parse error.

    A *missing* metrics file is a benign "no QA run yet" state
    (``available=False`` with a note, no error). A *present-but-malformed*
    file is an error state (parse error surfaced, never silently dropped).
    """
    if metrics_path is None:
        return QAHealth(available=False, error=None, source=None)
    try:
        raw = metrics_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _degraded_qa(metrics_path, f"cannot read qa_metrics: {exc}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _degraded_qa(metrics_path, f"qa_metrics JSON parse error: {exc}")
    if not isinstance(data, dict):
        return _degraded_qa(metrics_path, "qa_metrics is not a JSON object")
    return _qa_health_from_dict(metrics_path, data)


def _degraded_qa(path: Path, error: str) -> QAHealth:
    logger.warning("qa-health degraded (%s): %s", path, error)
    return QAHealth(available=False, error=error, source=str(path))


def _qa_health_from_dict(path: Path, data: dict[str, object]) -> QAHealth:
    def _int(key: str) -> int:
        val = data.get(key)
        return int(val) if isinstance(val, (int, float)) else 0

    def _str_map(key: str) -> dict[str, int]:
        val = data.get(key)
        if not isinstance(val, dict):
            return {}
        return {str(k): int(v) for k, v in val.items() if isinstance(v, (int, float))}

    top10_raw = data.get("findings_by_code_top10")
    top10: list[dict[str, int]] = []
    if isinstance(top10_raw, list):
        for entry in top10_raw:
            if isinstance(entry, dict) and "code" in entry and "count" in entry:
                top10.append({str(entry["code"]): int(entry["count"])})

    rate = data.get("clean_page_rate")
    return QAHealth(
        available=True,
        source=str(path),
        document_id=str(data["document_id"]) if "document_id" in data else None,
        edition=str(data["edition"]) if "edition" in data else None,
        pages_total=_int("pages_total"),
        clean_page_rate=float(rate) if isinstance(rate, (int, float)) else 0.0,
        blocking_count=_int("blocking_count"),
        waived_count=_int("waived_count"),
        findings_by_severity=_str_map("findings_by_severity"),
        findings_by_layer=_str_map("findings_by_layer"),
        findings_by_code_top10=top10,
    )


# --------------------------------------------------------------------------- #
# Code erosion (artifacts/code-erosion-review.json)
# --------------------------------------------------------------------------- #
class CodeErosion(BaseModel):
    available: bool
    error: str | None = None
    source: str | None = None
    base: str | None = None
    head: str | None = None
    files_changed: int = 0
    over_threshold_functions: int = 0
    total_erosion_score: int = 0
    new_functions: int = 0
    budget_violations: int = 0


def read_code_erosion(review_path: Path) -> CodeErosion:
    """Summarize the latest code-erosion review JSON if present.

    Missing file is benign (no review run yet). A present-but-malformed file
    surfaces the parse error so it is not silently treated as "no erosion".
    """
    if not review_path.is_file():
        return CodeErosion(available=False, error=None, source=None)
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("code-erosion degraded (%s): %s", review_path, exc)
        return CodeErosion(
            available=False, error=f"erosion review parse error: {exc}", source=str(review_path)
        )
    if not isinstance(data, dict):
        return CodeErosion(
            available=False, error="erosion review is not a JSON object", source=str(review_path)
        )
    structural = data.get("structural_erosion")
    structural = structural if isinstance(structural, dict) else {}
    verbosity = data.get("verbosity_drift")
    verbosity = verbosity if isinstance(verbosity, dict) else {}
    over = structural.get("over_threshold_functions")
    budget = data.get("budget_violations")
    return CodeErosion(
        available=True,
        source=str(review_path),
        base=str(data["base"]) if "base" in data else None,
        head=str(data["head"]) if "head" in data else None,
        files_changed=int(data.get("files_changed", 0) or 0),
        over_threshold_functions=len(over) if isinstance(over, list) else 0,
        total_erosion_score=int(structural.get("total_erosion_score", 0) or 0),
        new_functions=int(verbosity.get("new_functions", 0) or 0),
        budget_violations=len(budget) if isinstance(budget, list) else 0,
    )


# --------------------------------------------------------------------------- #
# Agent throughput (artifacts/run-issues-*.log)
# --------------------------------------------------------------------------- #
class AgentThroughput(BaseModel):
    available: bool
    error: str | None = None
    source: str | None = None
    shipped: int = 0
    total_attempted: int = 0
    failed_branches: list[str] = Field(default_factory=list)


_SUMMARY_RE = re.compile(r"Shipped:\s*(\d+)\s*/\s*(\d+)")
_FAILED_RE = re.compile(r"^\s*\[[\d:]+\]\s*Failed:\s*(.+?)\s*$")


def find_latest_run_issues_log(artifact_root: Path) -> Path | None:
    """Return the newest ``run-issues-*.log`` under *artifact_root* by name.

    The log filenames carry a sortable ``YYYYMMDD-HHMMSS`` stamp, so a plain
    reverse name sort yields the most recent run without a stat() per file.
    """
    logs = sorted(artifact_root.glob("run-issues-*.log"), reverse=True)
    return logs[0] if logs else None


def read_agent_throughput(log_path: Path | None) -> AgentThroughput:
    """Parse the most recent autonomous-runner log's ``=== Run summary ===``.

    A missing log is benign (runner never invoked). A present log without a
    parseable summary is reported ``available=False`` with a note rather than
    a fabricated zero-shipped success.
    """
    if log_path is None:
        return AgentThroughput(available=False, error=None, source=None)
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("agent-throughput degraded (%s): %s", log_path, exc)
        return AgentThroughput(
            available=False, error=f"cannot read run-issues log: {exc}", source=str(log_path)
        )
    match = _SUMMARY_RE.search(text)
    if match is None:
        return AgentThroughput(
            available=False,
            error="run-issues log has no '=== Run summary ===' line (run incomplete?)",
            source=str(log_path),
        )
    failed: list[str] = []
    for line in text.splitlines():
        fm = _FAILED_RE.match(line)
        if fm:
            failed = [b for b in fm.group(1).split() if b]
    return AgentThroughput(
        available=True,
        source=str(log_path),
        shipped=int(match.group(1)),
        total_attempted=int(match.group(2)),
        failed_branches=failed,
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
