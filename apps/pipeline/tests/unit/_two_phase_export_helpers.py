"""Shared fixture + seed helpers for the S5U-890 two-phase-commit export tests.

Split out of ``test_export_to_web_two_phase*.py`` so each test file stays under
the repo's 400-line ceiling. Mirrors the ``test_export_to_web_ref_binding``
harness: import ``export_to_web.py`` with ARTIFACT_ROOT / REGISTRY_PATH / REPO
redirected to a tmp dir, and seed complete runs (render result + page + QA +
optional glossary / facsimile raster) into a registry + artifact store.
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

from ._export_run_fixtures import add_run, write_render_result

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
    # the two-phase fixtures seed no doc1 config / PDF, so stub it to a no-op
    # here (image binding is exercised in test_export_to_web_image_binding).
    monkeypatch.setattr(mod, "verify_source_pdf_sha", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_load_facsimile_override_pids", lambda doc_id: [])
    yield mod
    sys.modules.pop("export_to_web", None)
    sys.modules.pop("_export_qa_gate", None)


def documents_root_for(tmp_path: Path) -> Path:
    """The redirected web documents root for an ``export_module`` run."""
    return tmp_path / "apps" / "web" / "public" / "documents"


def seed_run(  # noqa: PLR0913 — keyword-only test fixture builder
    artifact_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    started_at: str,
    edition: str,
    git_commit: str,
    page_text: str,
    with_glossary: bool = False,
    bad_internal_id: bool = False,
) -> str:
    """Seed a complete run; return the glossary ref (``""`` when none).

    ``with_glossary`` writes a glossary artifact + ref. ``bad_internal_id`` writes
    a render page whose internal ``page.id`` mismatches its filename, which makes
    ``run_export_validation`` fail at the post-build check (the G1-b surface).
    """
    pid = "p0001"
    render_ref = f"doc1/render/document/doc1/{run_id}.json"
    page_ref = f"doc1/render_page.v1/page/{pid}/{run_id}.json"
    page_path = artifact_root / page_ref
    page_path.parent.mkdir(parents=True, exist_ok=True)
    internal_id = "WRONG-ID" if bad_internal_id else pid
    page_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "document_version": edition,
                "page": {"id": internal_id, "page_id": pid, "title": f"Page {pid}"},
                "blocks": [
                    {
                        "kind": "paragraph",
                        "id": f"{pid}.b0",
                        "children": [{"kind": "text", "text": page_text}],
                    }
                ],
            }
        )
    )
    render_result: dict[str, object] = {"page_refs": {pid: page_ref}}
    glossary_ref = ""
    if with_glossary:
        glossary_ref = f"doc1/glossary/document/doc1/{run_id}.json"
        render_result["glossary_ref"] = glossary_ref
        gpath = artifact_root / glossary_ref
        gpath.parent.mkdir(parents=True, exist_ok=True)
        gpath.write_text(
            json.dumps({"entries": [{"term": f"t-{run_id}", "definition": page_text}]})
        )
    write_render_result(artifact_root, render_ref, render_result)
    qa_ref = _write_nonblocking_qa(artifact_root, run_id, edition)
    add_run(
        conn,
        run_id=run_id,
        started_at=started_at,
        edition=edition,
        git_commit=git_commit,
        render_ref=render_ref,
        qa_summary_ref=qa_ref,
    )
    return glossary_ref


def seed_facsimile_run(
    artifact_root: Path,
    conn: sqlite3.Connection,
    *,
    run_id: str,
    started_at: str,
    raster_bytes: bytes,
    write_raster: bool,
    pid: str = "p0007",
) -> None:
    """Seed a complete EN facsimile run (mirrors the rasters suite helper)."""
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
        rpath = artifact_root / raster_ref
        rpath.parent.mkdir(parents=True, exist_ok=True)
        rpath.write_bytes(raster_bytes)
    write_render_result(
        artifact_root,
        render_ref,
        {"page_refs": {pid: page_ref}, "raster_refs": {pid: {"150": raster_ref}}},
    )
    qa_ref = _write_nonblocking_qa(artifact_root, run_id, "en")
    add_run(
        conn,
        run_id=run_id,
        started_at=started_at,
        edition="en",
        render_ref=render_ref,
        qa_summary_ref=qa_ref,
    )


def _write_nonblocking_qa(artifact_root: Path, run_id: str, edition: str) -> str:
    """Write a non-blocking QA summary so the S5U-870 export gate allows; return its ref."""
    qa_ref = f"doc1/qa/document/doc1/{run_id}.json"
    qa_path = artifact_root / qa_ref
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(
        json.dumps(
            {
                "schema_version": "qa_summary.v1",
                "document_id": "doc1",
                "run_id": run_id,
                "edition": edition,
                "blocking": False,
                "record_refs": [],
                "review_pack_ref": "",
            }
        )
    )
    return qa_ref


def snapshot(documents_root: Path) -> dict[str, bytes]:
    """Read the whole doc1 bundle into {relpath: bytes} for byte-identity asserts.

    Skips this process's transient ``.stage-*`` / ``.backup-*`` dirs — those are
    swap scaffolding, not part of the published bundle.
    """
    base = documents_root / "doc1"
    out: dict[str, bytes] = {}
    if not base.exists():
        return out
    for p in sorted(base.rglob("*")):
        if any(part.startswith((".stage-", ".backup-")) for part in p.relative_to(base).parts):
            continue
        if p.is_file():
            out[str(p.relative_to(base))] = p.read_bytes()
    return out


def no_swap_litter(documents_root: Path) -> bool:
    """True when no transient staging/backup dirs remain next to the live bundle."""
    base = documents_root / "doc1"
    if not base.exists():
        return True
    return not any(d.name.startswith((".stage-", ".backup-")) for d in base.iterdir() if d.is_dir())
