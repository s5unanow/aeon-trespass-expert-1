"""Ref-bind exported images to the resolved run's source PDF (S5U-889).

S5U-869 made ``make export`` select pages / glossary / QA from a single resolved
run, but images were still re-extracted run-agnostically from the on-disk source
PDF (``extract_images``) with the resolved run's ``source_pdf_sha256`` never
checked. If the configured PDF is swapped between the run and the export, the
bundle gets images from a PDF the bound run never rendered against — a
cross-source splice for the image artifact class.

These tests cover the fix: ``verify_source_pdf_sha`` (unit) refuses on a
sha mismatch and skips the documented benign cases, and ``export_to_web.main``
(end-to-end) refuses with a non-zero exit and writes no bundle when the on-disk
PDF differs from the resolved run's recorded sha.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from atr_pipeline.utils.hashing import sha256_file

from ._export_run_fixtures import init_registry
from ._two_phase_export_helpers import seed_run

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "export_to_web.py"
IMAGES_HELPER_PATH = SCRIPTS_DIR / "_export_images.py"
WALKING_SKELETON_PDF = (
    REPO
    / "packages"
    / "fixtures"
    / "sample_documents"
    / "walking_skeleton"
    / "source"
    / "sample_page_01.pdf"
)


def _write_config_tree(root: Path, doc_id: str, source_pdf_relpath: str) -> None:
    """Write a minimal configs/ tree so load_document_config can resolve doc_id."""
    (root / ".git").mkdir(exist_ok=True)
    configs = root / "configs"
    (configs / "documents").mkdir(parents=True, exist_ok=True)
    (configs / "base.toml").write_text("")
    (configs / "documents" / f"{doc_id}.toml").write_text(
        textwrap.dedent(
            f"""
            [document]
            id = "{doc_id}"
            source_pdf = "{source_pdf_relpath}"
            """
        ).strip()
    )


@pytest.fixture()
def images_module() -> Iterator[ModuleType]:
    """Import scripts/_export_images.py as a module (for unit-testing the helper)."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("_export_images_s5u889", IMAGES_HELPER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_images_s5u889"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_images_s5u889", None)


@pytest.fixture()
def export_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[ModuleType]:
    """Import export_to_web.py with paths redirected to a tmp repo + real PDF.

    Unlike the ref-binding / two-phase fixtures, this leaves ``verify_source_pdf_sha``
    and ``extract_images`` *real* (that is the surface under test) and instead seeds
    a real doc1 config + on-disk source PDF under the tmp repo so the binding check
    can resolve and hash the PDF.
    """
    sys.path.insert(0, str(REPO / "apps" / "pipeline" / "src"))
    sys.path.insert(0, str(SCRIPTS_DIR))
    # Unlike the stubbed fixtures, this test exercises the REAL cross-module
    # ``verify_source_pdf_sha`` → ``RunResolutionError`` raise through
    # ``main()``'s ``except RunResolutionError`` clause. Earlier test files may
    # have left stale ``_export_run`` / ``_export_images`` instances in
    # sys.modules; reload the whole chain fresh so all three modules
    # (``export_to_web`` → ``_export_images`` → ``_export_run``) bind to ONE
    # ``RunResolutionError`` class object (otherwise the except clause silently
    # misses the raise — a test-harness module-caching artifact, not a bug).
    for _name in ("_export_run", "_export_images", "_export_qa_gate", "export_to_web"):
        sys.modules.pop(_name, None)
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
    # _load_facsimile_override_pids resolves config without repo_root (cwd
    # discovery), which won't find the tmp repo — stub it (no facsimile pages).
    monkeypatch.setattr(mod, "_load_facsimile_override_pids", lambda doc_id: [])
    # Seed a real doc1 config + on-disk source PDF under the tmp repo.
    pdf_dest = tmp_path / "materials" / "doc1.pdf"
    pdf_dest.parent.mkdir(parents=True)
    pdf_dest.write_bytes(WALKING_SKELETON_PDF.read_bytes())
    _write_config_tree(tmp_path, "doc1", "materials/doc1.pdf")
    yield mod
    sys.modules.pop("export_to_web", None)
    sys.modules.pop("_export_qa_gate", None)


def _seed_run_with_sha(export_module: ModuleType, tmp_path: Path, *, sha: str) -> None:
    """Seed a complete EN run whose recorded source_pdf_sha256 is *sha*."""
    conn = init_registry(tmp_path / "registry.db")
    seed_run(
        export_module.ARTIFACT_ROOT,
        conn,
        run_id="run_a",
        started_at="2026-01-01T00:00:00",
        edition="en",
        git_commit="commit_a",
        page_text="GOOD-A",
    )
    conn.execute("UPDATE runs SET source_pdf_sha256 = ? WHERE run_id = 'run_a'", (sha,))
    conn.commit()
    conn.close()


# --- Unit tests for the binding helper ---------------------------------------


def test_verify_source_pdf_sha_refuses_on_mismatch(
    images_module: ModuleType, tmp_path: Path
) -> None:
    """A recorded sha that differs from the on-disk PDF refuses (fail-closed, G1)."""
    _write_config_tree(tmp_path, "doc1", "materials/doc1.pdf")
    pdf_dest = tmp_path / "materials" / "doc1.pdf"
    pdf_dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_dest.write_bytes(WALKING_SKELETON_PDF.read_bytes())

    with pytest.raises(images_module.RunResolutionError, match="does not match"):
        images_module.verify_source_pdf_sha("doc1", ["deadbeef-wrong-sha"], repo_root=tmp_path)


def test_verify_source_pdf_sha_passes_on_match(images_module: ModuleType, tmp_path: Path) -> None:
    """The recorded sha equal to the on-disk PDF's sha does not raise."""
    _write_config_tree(tmp_path, "doc1", "materials/doc1.pdf")
    pdf_dest = tmp_path / "materials" / "doc1.pdf"
    pdf_dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_dest.write_bytes(WALKING_SKELETON_PDF.read_bytes())
    real_sha = sha256_file(pdf_dest)

    # Must not raise.
    images_module.verify_source_pdf_sha("doc1", [real_sha], repo_root=tmp_path)


def test_verify_source_pdf_sha_skips_when_pdf_absent(
    images_module: ModuleType, tmp_path: Path
) -> None:
    """A missing on-disk PDF is not a splice hazard (extract_images skips); no raise."""
    _write_config_tree(tmp_path, "doc1", "materials/does_not_exist.pdf")

    # Recorded sha present but no PDF on disk → cannot/needn't verify; no raise.
    images_module.verify_source_pdf_sha("doc1", ["any-recorded-sha"], repo_root=tmp_path)


def test_verify_source_pdf_sha_skips_when_recorded_sha_empty(
    images_module: ModuleType, tmp_path: Path
) -> None:
    """A legacy run with no recorded sha cannot be verified; skip rather than refuse."""
    _write_config_tree(tmp_path, "doc1", "materials/doc1.pdf")
    pdf_dest = tmp_path / "materials" / "doc1.pdf"
    pdf_dest.parent.mkdir(parents=True, exist_ok=True)
    pdf_dest.write_bytes(WALKING_SKELETON_PDF.read_bytes())

    # Empty recorded sha (the only "expected" value) → skip, no raise.
    images_module.verify_source_pdf_sha("doc1", [""], repo_root=tmp_path)


# --- End-to-end: main() refuses on a swapped PDF -----------------------------


def test_main_refuses_when_on_disk_pdf_differs_from_run_sha(
    export_module: ModuleType, tmp_path: Path
) -> None:
    """End-to-end: the on-disk PDF differs from run_a's recorded sha → export refuses.

    The fixture seeds run_a's pages from the registry but records a
    ``source_pdf_sha256`` that does NOT match the on-disk PDF (simulating a PDF
    swapped after the run rendered against it). Pre-fix, ``main`` extracted
    images from the swapped PDF and built the bundle anyway (silent cross-source
    splice). Post-fix, ``verify_source_pdf_sha`` refuses before any write.
    """
    _seed_run_with_sha(export_module, tmp_path, sha="0" * 64)  # never the real PDF sha
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    with pytest.raises(SystemExit) as exc:
        export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    assert exc.value.code == 1
    # No bundle was written for doc1 (refused before any phase-2 write).
    assert not (documents_root / "doc1" / "en").exists()
    # The shared images/ dir was not populated (extraction never ran).
    assert not (documents_root / "doc1" / "images").exists()


def test_main_proceeds_when_on_disk_pdf_matches_run_sha(
    export_module: ModuleType, tmp_path: Path
) -> None:
    """Happy path: a matching recorded sha lets the export build the bundle.

    Existing-behaviour pin: the binding check must not refuse when the PDF is
    unchanged (the common case). The bundle for run_a is written.
    """
    real_sha = sha256_file(tmp_path / "materials" / "doc1.pdf")
    _seed_run_with_sha(export_module, tmp_path, sha=real_sha)
    documents_root = tmp_path / "apps" / "web" / "public" / "documents"

    export_module.main(["--doc", "doc1", "--edition", "en", "--run-id", "run_a"])
    assert (documents_root / "doc1" / "en" / "manifest.json").exists()
