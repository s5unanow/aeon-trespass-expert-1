"""Regression tests for S5U-688: export_to_web image extraction must use
the selected document's configured source PDF and real page count, not a
repo-global hardcoded ATO path.

Separate file from test_export_to_web.py because that file is grandfathered
over the 400-line ceiling (S5U-677) and must not grow.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

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


@pytest.fixture()
def images_module() -> Iterator[ModuleType]:
    """Import scripts/_export_images.py as a module.

    Importing this directly (rather than via export_to_web) lets us exercise
    the helpers without running the top-level script's side-effecting
    ``sys.path`` inserts during collection order edge cases.
    """
    # Ensure scripts dir is importable so the helper can be loaded by name.
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location("_export_images_s5u688", IMAGES_HELPER_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_images_s5u688"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_images_s5u688", None)


@pytest.fixture()
def export_module() -> Iterator[ModuleType]:
    """Import export_to_web.py as a module, cleaning up sys.modules after."""
    spec = importlib.util.spec_from_file_location("export_to_web_s5u688", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_to_web_s5u688"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("export_to_web_s5u688", None)


def _write_config_tree(root: Path, doc_id: str, source_pdf_relpath: str) -> None:
    """Write a minimal configs/ tree so load_document_config can resolve doc_id."""
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


def test_resolve_source_pdf_for_custom_doc(images_module: ModuleType, tmp_path: Path) -> None:
    """S5U-688 red-before: the script must expose a helper that returns the
    per-document source PDF path (not a repo-global constant).

    Pre-fix (SHA a66276a), ``export_to_web`` has no ``_resolve_source_pdf``
    helper and ``PDF_PATH`` is a module-level constant pointing at the ATO
    rulebook. Accessing the helper raises AttributeError.
    """
    # Fake repo layout; reuse the walking-skeleton fixture PDF as the
    # "custom doc" source so PyMuPDF can open it.
    (tmp_path / ".git").mkdir()
    pdf_dest_rel = "materials/custom.pdf"
    pdf_dest = tmp_path / pdf_dest_rel
    pdf_dest.parent.mkdir(parents=True)
    pdf_dest.write_bytes(WALKING_SKELETON_PDF.read_bytes())
    _write_config_tree(tmp_path, "custom_doc", pdf_dest_rel)

    pdf_path, page_count = images_module.resolve_source_pdf("custom_doc", repo_root=tmp_path)
    assert pdf_path == pdf_dest
    assert page_count == 1


def test_resolve_source_pdf_for_walking_skeleton_uses_real_pdf(
    images_module: ModuleType,
) -> None:
    """Walking-skeleton config resolves to its 1-page fixture PDF, not the ATO PDF.

    Uses the real repo configs/ tree — no tmp_path needed.
    """
    assert WALKING_SKELETON_PDF.exists(), (
        "Fixture precondition: walking_skeleton source PDF must exist"
    )
    pdf_path, page_count = images_module.resolve_source_pdf("walking_skeleton", repo_root=REPO)
    assert pdf_path == WALKING_SKELETON_PDF
    # Walking skeleton fixture is a single-page PDF (per source_manifest).
    assert page_count == 1


def test_extract_images_bounded_by_real_page_count(
    images_module: ModuleType, tmp_path: Path
) -> None:
    """S5U-688 red-before: extract_images must only iterate up to the selected
    doc's real page count, not the hardcoded range(1, 84).

    Pre-fix, extract_images(doc_id='walking_skeleton', ...) would either look
    at ATO's PDF_PATH (missing under tmp_path) or — if given walking_skeleton
    config — still probe pages 1..83 of a 1-page PDF, raising or silently
    skipping 82 pages.

    Under the fix, extract_page_images is called exactly once (page 1) for
    the walking-skeleton fixture.
    """
    doc_public = tmp_path / "web" / "documents" / "walking_skeleton"
    doc_public.mkdir(parents=True)

    observed_calls: list[tuple[Path, int]] = []

    def fake_extract(
        pdf_path: Path,
        *,
        page_number: int,
        min_width: int = 0,
        min_height: int = 0,
    ) -> list[object]:
        observed_calls.append((Path(pdf_path), page_number))
        return []

    with patch(
        "atr_pipeline.services.pdf.image_extractor.extract_page_images",
        side_effect=fake_extract,
    ):
        result = images_module.extract_images("walking_skeleton", doc_public, repo_root=REPO)

    assert result == {}
    assert len(observed_calls) == 1, (
        f"Expected exactly 1 page probe for walking_skeleton (1-page PDF); "
        f"got {len(observed_calls)}: {observed_calls}"
    )
    assert observed_calls[0] == (WALKING_SKELETON_PDF.resolve(), 1)


def test_extract_images_missing_pdf_returns_empty(
    images_module: ModuleType, tmp_path: Path
) -> None:
    """Regression pin: if the resolved source PDF does not exist on disk, the
    script must skip extraction and return {} (preserves pre-fix guard
    behaviour). No new branch coverage — existing-behaviour pin.
    """
    (tmp_path / ".git").mkdir()
    missing_pdf_relpath = "materials/does_not_exist.pdf"
    _write_config_tree(tmp_path, "phantom_doc", missing_pdf_relpath)
    doc_public = tmp_path / "public"
    doc_public.mkdir()

    result = images_module.extract_images("phantom_doc", doc_public, repo_root=tmp_path)
    assert result == {}


def test_extract_images_ato_default_resolves_ato_config(
    images_module: ModuleType,
) -> None:
    """Regression pin: default --doc=ato_core_v1_1 must resolve to
    materials/ATO_CORE_Rulebook_v1.1.pdf (per configs/documents/ato_core_v1_1.toml).

    This is the "must-not-break current ATO behaviour" invariant from the
    Linear issue. Existing-behaviour pin (no new branch coverage).
    """
    pdf_path, page_count = images_module.resolve_source_pdf("ato_core_v1_1", repo_root=REPO)
    assert pdf_path == REPO / "materials" / "ATO_CORE_Rulebook_v1.1.pdf"
    # If the real ATO PDF is checked in, page_count should be 83 per ingest
    # manifest. If it is absent (CI / lite clone), the resolver still returns
    # a path and page_count defaults to 0 so the call-site guard kicks in.
    if pdf_path.exists():
        assert page_count == 83
    else:
        assert page_count == 0


def test_extract_images_reexported_from_export_to_web(export_module: ModuleType) -> None:
    """``extract_images`` and ``resolve_source_pdf`` must be importable from the
    main entry script so existing call-sites (including prior tests and
    ``main()``) keep working after S5U-688 split the helpers into
    ``_export_images.py``.
    """
    assert callable(getattr(export_module, "extract_images", None))
    assert callable(getattr(export_module, "resolve_source_pdf", None))
