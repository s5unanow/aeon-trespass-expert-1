"""Tests for scripts/export_to_web.py edition-scoped export."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO / "scripts" / "export_to_web.py"


@pytest.fixture()
def export_module() -> Iterator[ModuleType]:
    """Import export_to_web.py as a module, cleaning up sys.modules after."""
    spec = importlib.util.spec_from_file_location("export_to_web", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["export_to_web"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("export_to_web", None)


def _make_render_page(
    page_id: str,
    has_cyrillic: bool = False,
    has_marks: bool = False,
    block_count: int = 3,
) -> dict:
    """Build a minimal render page dict for scoring tests."""
    text = "Пример текста" if has_cyrillic else "Example text"
    children = [{"kind": "text", "text": text}]
    if has_marks:
        children.append({"kind": "text", "text": "bold", "marks": [{"type": "bold"}]})
    blocks = [
        {"kind": "paragraph", "id": f"{page_id}.b{i}", "children": children}
        for i in range(block_count)
    ]
    return {
        "schema_version": "1.0",
        "page": {"page_id": page_id, "title": f"Page {page_id}"},
        "blocks": blocks,
    }


class TestScoreRender:
    def test_ru_prefers_cyrillic(self, export_module: ModuleType) -> None:
        ru_page = _make_render_page("p0001", has_cyrillic=True)
        en_page = _make_render_page("p0001", has_cyrillic=False)
        assert export_module.score_render(ru_page, "ru") > export_module.score_render(en_page, "ru")

    def test_en_prefers_latin(self, export_module: ModuleType) -> None:
        ru_page = _make_render_page("p0001", has_cyrillic=True)
        en_page = _make_render_page("p0001", has_cyrillic=False)
        assert export_module.score_render(en_page, "en") > export_module.score_render(ru_page, "en")

    def test_marks_increase_score(self, export_module: ModuleType) -> None:
        plain = _make_render_page("p0001")
        marked = _make_render_page("p0001", has_marks=True)
        assert export_module.score_render(marked, "en") > export_module.score_render(plain, "en")


class TestParseArgs:
    def test_defaults(self, export_module: ModuleType) -> None:
        args = export_module._parse_args([])
        assert args.doc == "ato_core_v1_1"
        assert args.edition == "all"

    def test_edition_en(self, export_module: ModuleType) -> None:
        args = export_module._parse_args(["--edition", "en"])
        assert args.edition == "en"

    def test_custom_doc(self, export_module: ModuleType) -> None:
        args = export_module._parse_args(["--doc", "walking_skeleton"])
        assert args.doc == "walking_skeleton"


class TestExportPages:
    def _setup_render_artifacts(
        self, tmp_path: Path, doc_id: str, pages: list[str], has_cyrillic: bool = False
    ) -> Path:
        """Create fake render artifacts and return the render_src path."""
        render_src = tmp_path / "artifacts" / doc_id / "render_page.v1" / "page"
        for pid in pages:
            page_dir = render_src / pid
            page_dir.mkdir(parents=True, exist_ok=True)
            data = _make_render_page(pid, has_cyrillic=has_cyrillic)
            (page_dir / "hash_001.json").write_text(json.dumps(data))
        return render_src

    def test_en_edition_writes_to_edition_subdir(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        render_src = self._setup_render_artifacts(tmp_path, "doc1", ["p0001", "p0002"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        assert (doc_public / "en" / "data" / "render_page.p0001.json").exists()
        assert (doc_public / "en" / "data" / "render_page.p0002.json").exists()
        assert (doc_public / "en" / "manifest.json").exists()
        # Root-level data dir should NOT exist
        assert not (doc_public / "data").exists()

    def test_ru_edition_writes_to_edition_subdir(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        render_src = self._setup_render_artifacts(tmp_path, "doc1", ["p0001"], has_cyrillic=True)
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "ru", render_src, doc_public, {})

        assert (doc_public / "ru" / "data" / "render_page.p0001.json").exists()
        assert (doc_public / "ru" / "manifest.json").exists()

    def test_manifest_contains_page_list(self, tmp_path: Path, export_module: ModuleType) -> None:
        render_src = self._setup_render_artifacts(tmp_path, "doc1", ["p0001", "p0002"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert manifest["document_id"] == "doc1"
        page_ids = [p["page_id"] for p in manifest["pages"]]
        assert page_ids == ["p0001", "p0002"]

    def test_both_editions_coexist(self, tmp_path: Path, export_module: ModuleType) -> None:
        render_src = self._setup_render_artifacts(tmp_path, "doc1", ["p0001"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})
        export_module.export_pages("doc1", "ru", render_src, doc_public, {})

        assert (doc_public / "en" / "manifest.json").exists()
        assert (doc_public / "ru" / "manifest.json").exists()

    def test_navigation_links(self, tmp_path: Path, export_module: ModuleType) -> None:
        render_src = self._setup_render_artifacts(tmp_path, "doc1", ["p0001", "p0002", "p0003"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        p1 = json.loads((doc_public / "en" / "data" / "render_page.p0001.json").read_text())
        assert p1["nav"]["prev"] is None
        assert p1["nav"]["next"] == "p0002"

        p2 = json.loads((doc_public / "en" / "data" / "render_page.p0002.json").read_text())
        assert p2["nav"]["prev"] == "p0001"
        assert p2["nav"]["next"] == "p0003"

        p3 = json.loads((doc_public / "en" / "data" / "render_page.p0003.json").read_text())
        assert p3["nav"]["prev"] == "p0002"
        assert p3["nav"]["next"] is None
