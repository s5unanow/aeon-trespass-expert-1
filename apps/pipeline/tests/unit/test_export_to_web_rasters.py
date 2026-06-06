"""End-to-end run-bound facsimile raster export (S5U-891).

Drives ``export_to_web.main()`` against a registry + artifact-store fixture with
facsimile pages and asserts:

* The exported raster for a facsimile page comes from the *resolved* run's
  ``raster_refs`` — a second run with different raster content never splices in
  (the S5U-891 cross-run hazard). Pinning ``--run-id`` selects that run's raster.
* Fail-closed (guards.md Rule G1): when a bound raster ref's file is missing on
  disk, the export refuses (``RunResolutionError`` → ``SystemExit(1)``) rather
  than silently falling back to a global ``release/rasters`` / newest-meta scan.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from ._export_run_fixtures import add_run, init_registry, write_render_result

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "export_to_web.py"


@pytest.fixture()
def export_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[ModuleType]:
    """Import export_to_web.py with paths redirected to tmp (mirrors ref-binding suite)."""
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    gate_spec = importlib.util.spec_from_file_location(
        "_export_qa_gate", SCRIPTS_DIR / "_export_qa_gate.py"
    )
    assert gate_spec is not None and gate_spec.loader is not None
    gate_mod = importlib.util.module_from_spec(gate_spec)
    sys.modules["_export_qa_gate"] = gate_mod
    gate_spec.loader.exec_module(gate_mod)
    monkeypatch.setattr(gate_mod, "resolve_block_on", lambda doc_id: {"error", "critical"})

    spec = importlib.util.spec_from_file_location("export_to_web", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_to_web"] = mod
    spec.loader.exec_module(mod)

    artifact_root = tmp_path / "artifacts"
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"
    documents_root.mkdir(parents=True)
    monkeypatch.setattr(mod, "ARTIFACT_ROOT", artifact_root)
    monkeypatch.setattr(mod, "REGISTRY_PATH", tmp_path / "registry.db")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "extract_images", lambda *a, **k: {})
    # The S5U-889 on-disk-PDF binding check resolves doc config + reads the PDF;
    # this fixture seeds no doc1 config / PDF, so stub it to a no-op here (image
    # binding is exercised in test_export_to_web_image_binding).
    monkeypatch.setattr(mod, "verify_source_pdf_sha", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_load_facsimile_override_pids", lambda doc_id: [])
    yield mod
    sys.modules.pop("export_to_web", None)
    sys.modules.pop("_export_qa_gate", None)


def _seed_facsimile_run(
    artifact_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    started_at: str,
    raster_bytes: bytes,
    write_raster: bool = True,
    pid: str = "p0007",
) -> None:
    """Seed a complete EN run whose single page is a facsimile with one raster level.

    ``write_raster=False`` records the raster ref in the render result but does
    NOT write the PNG to disk — the fail-closed scenario.
    """
    render_ref = f"doc1/render/document/doc1/{run_id}.json"
    page_ref = f"doc1/render_page.v1/page/{pid}/{run_id}.json"
    raster_ref = f"doc1/raster.v1/page/{pid}/{run_id}__150dpi.png"

    page_path = artifact_root / page_ref
    page_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_version": "en",
                "presentation_mode": "facsimile",
                "page": {"page_id": pid, "title": f"Page {pid}"},
                "facsimile": {
                    "raster_src": f"rasters/{pid}__150dpi.png",
                    "raster_src_hires": f"rasters/{pid}__150dpi.png",
                },
                "blocks": [],
            }
        )
    )
    if write_raster:
        raster_path = artifact_root / raster_ref
        raster_path.parent.mkdir(parents=True, exist_ok=True)
        raster_path.write_bytes(raster_bytes)

    write_render_result(
        artifact_root,
        render_ref,
        {"page_refs": {pid: page_ref}, "raster_refs": {pid: {"150": raster_ref}}},
    )
    qa_ref = f"doc1/qa/document/doc1/{run_id}.json"
    qa_path = artifact_root / qa_ref
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": "doc1",
                "run_id": run_id,
                "edition": "en",
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )
    add_run(
        conn,
        run_id=run_id,
        started_at=started_at,
        edition="en",
        render_ref=render_ref,
        qa_summary_ref=qa_ref,
    )


def test_raster_bound_to_resolved_run_not_newest(export_module: ModuleType, tmp_path: Path) -> None:
    """The exported raster comes from the resolved run, never the other run's PNG."""
    conn = init_registry(tmp_path / "registry.db")
    _seed_facsimile_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        raster_bytes=b"RASTER-A-BYTES",
    )
    _seed_facsimile_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_b",
        started_at="2026-02-01T00:00:00",
        raster_bytes=b"RASTER-B-BYTES",
    )
    conn.close()
    rasters_dir = tmp_path / "apps" / "web" / "public" / "documents" / "doc1" / "rasters"

    # Pin run A explicitly: the exported raster must be A's bytes even though run B
    # is newer (the pre-fix global scan would have picked the newest / last-written).
    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    assert (rasters_dir / "p0007__150dpi.png").read_bytes() == b"RASTER-A-BYTES"

    # Default latest-complete resolves run B → B's raster bytes.
    export_module.main(["--doc", "doc1", "--edition", "en"])
    assert (rasters_dir / "p0007__150dpi.png").read_bytes() == b"RASTER-B-BYTES"


def test_missing_bound_raster_file_refuses(export_module: ModuleType, tmp_path: Path) -> None:
    """G1 fail-closed: a bound raster ref missing on disk refuses (no global fallback)."""
    conn = init_registry(tmp_path / "registry.db")
    # Plant a stray global release raster the pre-fix scan would have used — the
    # run-bound path must NOT fall back to it.
    release_dir = export_module.ARTIFACT_ROOT / "doc1" / "release" / "rasters"
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "p0007__150dpi.png").write_bytes(b"STRAY-GLOBAL-RASTER")

    _seed_facsimile_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        raster_bytes=b"unused",
        write_raster=False,  # ref recorded, file absent → must refuse
    )
    conn.close()

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en"])
    assert exc.value.code == 1
    # The stray global raster must NOT have been spliced into the bundle.
    rasters_dir = tmp_path / "apps" / "web" / "public" / "documents" / "doc1" / "rasters"
    assert not (rasters_dir / "p0007__150dpi.png").exists()
