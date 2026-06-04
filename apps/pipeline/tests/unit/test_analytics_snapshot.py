"""Tests for scripts/analytics_snapshot.py and its source readers.

Covers the happy path plus the three fail-closed must-refuse cases from
S5U-873 (.claude/rules/guards.md G1 spirit, adapted for a read-only
aggregator):

* registry unreadable / missing / schema mismatch -> degraded snapshot
  (``degraded=True``, ``run_health.available=False``) AND non-zero exit;
  never a silent empty success masquerading as healthy.
* qa_metrics malformed -> parse error surfaced in ``qa_health.error``;
  QA health is never silently dropped, and the snapshot exits non-zero.
* git / gh subprocess failure -> only that field is marked unavailable;
  the whole snapshot is NOT aborted.

Also asserts the aggregator is pure read-only (registry file unchanged).
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_DIR = REPO / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def mods() -> Iterator[tuple[ModuleType, ModuleType, ModuleType]]:
    """Import the three analytics modules with scripts/ on sys.path."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        sources = _load("_analytics_sources")
        network = _load("_analytics_network")
        snapshot = _load("analytics_snapshot")
        yield snapshot, sources, network
    finally:
        for name in ("analytics_snapshot", "_analytics_sources", "_analytics_network"):
            sys.modules.pop(name, None)
        if str(SCRIPT_DIR) in sys.path:
            sys.path.remove(str(SCRIPT_DIR))


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #
def _make_registry(path: Path) -> None:
    """Create a healthy registry with the production schema + one run/event."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE runs (
            run_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
            pipeline_version TEXT NOT NULL, config_hash TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'running'
        );
        CREATE TABLE stage_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
            stage_name TEXT NOT NULL, scope TEXT NOT NULL, entity_id TEXT NOT NULL,
            cache_key TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'started',
            started_at TEXT NOT NULL, finished_at TEXT, artifact_ref TEXT,
            error_message TEXT, duration_ms INTEGER
        );
        """
    )
    conn.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?)",
        (
            "run_1",
            "ato_core_v1_1",
            "0.1.0",
            "abc",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:01:00+00:00",
            "completed",
        ),
    )
    conn.execute(
        "INSERT INTO stage_events"
        " (run_id, stage_name, scope, entity_id, cache_key, status, started_at, duration_ms)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("run_1", "render", "page", "p1", "k1", "completed", "2026-01-01T00:00:00+00:00", 500),
    )
    conn.commit()
    conn.close()


_QA_METRICS = {
    "schema_version": "qa_metrics.v1",
    "document_id": "ato_core_v1_1",
    "edition": "en",
    "pages_total": 10,
    "clean_page_rate": 0.5,
    "blocking_count": 3,
    "waived_count": 1,
    "findings_by_severity": {"error": 3, "warning": 2},
    "findings_by_layer": {"terminology": 4},
    "findings_by_code_top10": [{"code": "UNTRANSLATED_TEXT", "count": 4}],
}


def _write_qa_metrics(artifact_root: Path, doc: str, payload: object) -> Path:
    mdir = artifact_root / doc / "qa_metrics.v1" / "document" / doc
    mdir.mkdir(parents=True, exist_ok=True)
    p = mdir / "deadbeef.json"
    p.write_text(json.dumps(payload) if not isinstance(payload, str) else payload)
    return p


def _build(snapshot: ModuleType, tmp_path: Path, **over: object) -> Any:
    kwargs: dict[str, object] = {
        "document_id": "ato_core_v1_1",
        "registry_path": tmp_path / "registry.db",
        "artifact_root": tmp_path / "artifacts",
        "erosion_review_path": tmp_path / "missing-erosion.json",
        "repo_root": tmp_path,
        "include_network": False,
    }
    kwargs.update(over)
    return snapshot.build_snapshot(**kwargs)


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_happy_path_writes_valid_healthy_snapshot(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _sources, _net = mods
    _make_registry(tmp_path / "registry.db")
    _write_qa_metrics(tmp_path / "artifacts", "ato_core_v1_1", _QA_METRICS)

    snap = _build(snapshot, tmp_path)
    assert snap.degraded is False
    assert snap.run_health.available is True
    assert snap.run_health.total_runs == 1
    assert snap.qa_health.available is True
    assert snap.qa_health.blocking_count == 3
    assert any(s.stage_name == "render" for s in snap.run_health.stage_durations)


def test_main_writes_atomic_valid_json_and_exits_zero(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _s, _n = mods
    _make_registry(tmp_path / "registry.db")
    _write_qa_metrics(tmp_path / "artifacts", "ato_core_v1_1", _QA_METRICS)
    out = tmp_path / "out" / "latest.json"
    rc = snapshot.main(
        [
            "--registry",
            str(tmp_path / "registry.db"),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--erosion-review",
            str(tmp_path / "nope.json"),
            "--output",
            str(out),
            "--no-network",
        ]
    )
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["schema_version"] == "analytics_snapshot.v1"
    assert data["degraded"] is False


# --------------------------------------------------------------------------- #
# Must-refuse 1: registry unreadable / missing / schema mismatch
# --------------------------------------------------------------------------- #
def test_missing_registry_is_degraded_not_silent_healthy(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _s, _n = mods
    # No registry written, no qa metrics.
    snap = _build(snapshot, tmp_path)
    assert snap.run_health.available is False
    assert snap.run_health.error and "registry not found" in snap.run_health.error
    assert snap.degraded is True
    assert any("run_health" in r for r in snap.degraded_reasons)
    # Critically: not a healthy empty success.
    assert snap.run_health.total_runs == 0


def test_unreadable_registry_main_exits_nonzero(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _s, _n = mods
    # A file that is not a valid sqlite DB -> open succeeds, query fails.
    bad = tmp_path / "registry.db"
    bad.write_text("this is not sqlite")
    out = tmp_path / "latest.json"
    rc = snapshot.main(
        [
            "--registry",
            str(bad),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--output",
            str(out),
            "--no-network",
        ]
    )
    assert rc == 1
    data = json.loads(out.read_text())
    assert data["degraded"] is True
    assert data["run_health"]["available"] is False


def test_schema_mismatch_registry_is_degraded(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    _snap, sources, _n = mods
    reg = tmp_path / "registry.db"
    conn = sqlite3.connect(str(reg))
    # 'runs' exists but is missing required columns (schema mismatch).
    conn.executescript("CREATE TABLE runs (run_id TEXT, document_id TEXT);")
    conn.commit()
    conn.close()
    health = sources.read_run_health(reg)
    assert health.available is False
    assert health.error and "missing columns" in health.error


# --------------------------------------------------------------------------- #
# Must-refuse 2: qa_metrics malformed -> parse error surfaced, not dropped
# --------------------------------------------------------------------------- #
def test_malformed_qa_metrics_surfaces_parse_error(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _s, _n = mods
    _make_registry(tmp_path / "registry.db")
    _write_qa_metrics(tmp_path / "artifacts", "ato_core_v1_1", "{not valid json")
    snap = _build(snapshot, tmp_path)
    assert snap.qa_health.available is False
    assert snap.qa_health.error and "parse error" in snap.qa_health.error.lower()
    # QA degradation must mark the whole snapshot degraded (don't drop silently).
    assert snap.degraded is True
    assert any("qa_health" in r for r in snap.degraded_reasons)


def test_missing_qa_metrics_is_benign_not_degraded(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, _s, _n = mods
    _make_registry(tmp_path / "registry.db")
    # No qa metrics written at all -> benign "no QA run yet", not an error.
    snap = _build(snapshot, tmp_path)
    assert snap.qa_health.available is False
    assert snap.qa_health.error is None
    assert snap.degraded is False


# --------------------------------------------------------------------------- #
# Must-refuse 3: git/gh failure marks only that field, never aborts snapshot
# --------------------------------------------------------------------------- #
def test_network_failure_marks_field_only(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, _s, network = mods
    _make_registry(tmp_path / "registry.db")
    _write_qa_metrics(tmp_path / "artifacts", "ato_core_v1_1", _QA_METRICS)

    def _boom(_cmd: list[str], **_kw: object) -> object:
        raise OSError("git not found")

    monkeypatch.setattr(network, "_run", _boom)
    snap = _build(snapshot, tmp_path, include_network=True)
    # Network signals failed...
    assert snap.network.git_available is False
    assert snap.network.git_error and "git" in snap.network.git_error
    assert snap.network.gh_available is False
    # ...but the snapshot is NOT aborted and core signals stay healthy.
    assert snap.degraded is False
    assert snap.run_health.available is True
    assert snap.qa_health.available is True


def test_gh_nonzero_exit_marks_gh_unavailable(
    mods: tuple[ModuleType, ModuleType, ModuleType], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _snapshot, _s, network = mods

    class _Proc:
        def __init__(self, rc: int, out: str, err: str) -> None:
            self.returncode, self.stdout, self.stderr = rc, out, err

    def _fake_run(cmd: list[str], **_kw: object) -> object:
        if cmd[0] == "git":
            return _Proc(0, "main\nfeature\n", "")
        return _Proc(1, "", "gh: not authenticated")

    monkeypatch.setattr(network, "_run", _fake_run)
    signals = network.read_network_signals(tmp_path)
    assert signals.git_available is True
    assert signals.gh_available is False
    assert signals.gh_error and "gh run list failed" in signals.gh_error


# --------------------------------------------------------------------------- #
# Read-only guarantee
# --------------------------------------------------------------------------- #
def test_reader_does_not_mutate_registry(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    snapshot, sources, _n = mods
    reg = tmp_path / "registry.db"
    _make_registry(reg)
    before = reg.read_bytes()
    sources.read_run_health(reg)
    snapshot.build_snapshot(
        document_id="ato_core_v1_1",
        registry_path=reg,
        artifact_root=tmp_path / "artifacts",
        erosion_review_path=tmp_path / "nope.json",
        repo_root=tmp_path,
        include_network=False,
    )
    assert reg.read_bytes() == before


# --------------------------------------------------------------------------- #
# Agent throughput + code erosion parsing
# --------------------------------------------------------------------------- #
def test_agent_throughput_parses_run_summary(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    _snap, sources, _n = mods
    log = tmp_path / "run-issues-20260101-000000.log"
    log.write_text(
        "[00:00:00] === Run summary ===\n"
        "[00:00:00] Shipped: 8/10\n"
        "[00:00:00]   OK:     issue-1 issue-2\n"
        "[00:00:00]   Failed: s5unanow/s5u-1-x s5unanow/s5u-2-y\n"
    )
    tp = sources.read_agent_throughput(log)
    assert tp.available is True
    assert tp.shipped == 8 and tp.total_attempted == 10
    assert tp.failed_branches == ["s5unanow/s5u-1-x", "s5unanow/s5u-2-y"]


def test_malformed_erosion_review_surfaces_error(
    mods: tuple[ModuleType, ModuleType, ModuleType], tmp_path: Path
) -> None:
    _snap, sources, _n = mods
    review = tmp_path / "code-erosion-review.json"
    review.write_text("{ broken json")
    res = sources.read_code_erosion(review)
    assert res.available is False
    assert res.error and "parse error" in res.error.lower()
