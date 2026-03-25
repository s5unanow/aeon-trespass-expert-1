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


class TestPickLatest:
    def test_picks_most_recently_modified(self, tmp_path: Path, export_module: ModuleType) -> None:
        """The newest file by mtime wins, regardless of content."""
        import time

        old = tmp_path / "old.json"
        old.write_text('{"v": "old"}')

        time.sleep(0.05)
        new = tmp_path / "new.json"
        new.write_text('{"v": "new"}')

        result = export_module._pick_latest([old, new])
        assert result == new

    def test_newer_filtered_facsimile_beats_stale_unfiltered(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression: newer quality-filtered artifact must beat stale one with more annotations."""
        import time

        stale = tmp_path / "stale.json"
        stale.write_text(
            json.dumps(
                {
                    "presentation_mode": "facsimile",
                    "facsimile": {"annotations": [{"text": "T"}] * 56},
                    "blocks": [],
                }
            )
        )

        time.sleep(0.05)
        filtered = tmp_path / "filtered.json"
        filtered.write_text(
            json.dumps(
                {
                    "presentation_mode": "facsimile",
                    "facsimile": {"annotations": [{"text": "T"}] * 31},
                    "blocks": [],
                }
            )
        )

        result = export_module._pick_latest([stale, filtered])
        assert result == filtered


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


class TestBuildDocumentIndex:
    def test_empty_directory(self, tmp_path: Path, export_module: ModuleType) -> None:
        docs_root = tmp_path / "documents"
        docs_root.mkdir()
        result = export_module._build_document_index(docs_root)
        assert result == []

    def test_nonexistent_directory(self, tmp_path: Path, export_module: ModuleType) -> None:
        result = export_module._build_document_index(tmp_path / "missing")
        assert result == []

    def test_single_doc_single_edition(self, tmp_path: Path, export_module: ModuleType) -> None:
        docs_root = tmp_path / "documents"
        (docs_root / "doc1" / "en").mkdir(parents=True)
        (docs_root / "doc1" / "en" / "manifest.json").write_text("{}")
        result = export_module._build_document_index(docs_root)
        assert result == [{"document_id": "doc1", "editions": ["en"]}]

    def test_multiple_docs_and_editions(self, tmp_path: Path, export_module: ModuleType) -> None:
        docs_root = tmp_path / "documents"
        for doc, editions in [("aaa", ["en", "ru"]), ("bbb", ["en"])]:
            for ed in editions:
                (docs_root / doc / ed).mkdir(parents=True)
                (docs_root / doc / ed / "manifest.json").write_text("{}")
        result = export_module._build_document_index(docs_root)
        assert result == [
            {"document_id": "aaa", "editions": ["en", "ru"]},
            {"document_id": "bbb", "editions": ["en"]},
        ]

    def test_root_level_manifest_indexed_as_default(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Root-level-only manifest gets synthetic 'default' edition."""
        docs_root = tmp_path / "documents"
        (docs_root / "doc1").mkdir(parents=True)
        (docs_root / "doc1" / "manifest.json").write_text("{}")
        result = export_module._build_document_index(docs_root)
        assert result == [{"document_id": "doc1", "editions": ["default"]}]

    def test_edition_manifest_takes_precedence_over_root(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """When both root and edition manifests exist, only editions are listed."""
        docs_root = tmp_path / "documents"
        (docs_root / "doc1" / "en").mkdir(parents=True)
        (docs_root / "doc1" / "en" / "manifest.json").write_text("{}")
        (docs_root / "doc1" / "manifest.json").write_text("{}")
        result = export_module._build_document_index(docs_root)
        assert result == [{"document_id": "doc1", "editions": ["en"]}]

    def test_skips_dirs_without_manifest(self, tmp_path: Path, export_module: ModuleType) -> None:
        docs_root = tmp_path / "documents"
        (docs_root / "doc1" / "en").mkdir(parents=True)
        (docs_root / "doc1" / "en" / "manifest.json").write_text("{}")
        # images dir has no manifest — should be ignored
        (docs_root / "doc1" / "images").mkdir(parents=True)
        result = export_module._build_document_index(docs_root)
        assert result == [{"document_id": "doc1", "editions": ["en"]}]


class TestWriteDocumentIndex:
    def test_writes_index_json(self, tmp_path: Path, export_module: ModuleType) -> None:
        docs_root = tmp_path / "documents"
        (docs_root / "doc1" / "en").mkdir(parents=True)
        (docs_root / "doc1" / "en" / "manifest.json").write_text("{}")
        export_module.write_document_index(docs_root)
        index = json.loads((docs_root / "index.json").read_text())
        assert index == {"documents": [{"document_id": "doc1", "editions": ["en"]}]}


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

    def test_facsimile_pages_skip_image_injection(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Facsimile pages skip postprocessing and image injection."""
        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0007"
        page_dir.mkdir(parents=True, exist_ok=True)
        facsimile_page = {
            "schema_version": "1.0",
            "presentation_mode": "facsimile",
            "page": {"page_id": "p0007", "title": "Components"},
            "blocks": [{"kind": "paragraph", "id": "p0007.b1", "children": []}],
            "facsimile": {
                "raster_src": "rasters/p0007__150dpi.png",
                "raster_src_hires": "rasters/p0007__300dpi.png",
                "width_px": 1240,
                "height_px": 1754,
            },
        }
        (page_dir / "hash_001.json").write_text(json.dumps(facsimile_page))
        doc_public = tmp_path / "web" / "documents" / "doc1"

        # Pass image data — should NOT be injected for facsimile page
        images = {"p0007": [{"asset_id": "img0051", "src": "/img.png", "alt": "x"}]}
        export_module.export_pages("doc1", "en", render_src, doc_public, images)

        exported = json.loads((doc_public / "en" / "data" / "render_page.p0007.json").read_text())
        assert exported["presentation_mode"] == "facsimile"
        # Raster URLs rewritten to web-public paths
        assert "/documents/doc1/rasters/" in exported["facsimile"]["raster_src"]
        # No synthetic figure blocks injected
        assert not any(b.get("asset_id") == "img0051" for b in exported.get("blocks", []))

    def test_export_picks_latest_artifact_not_highest_annotation_count(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-392: newer quality-filtered artifact must win over stale one."""
        import time

        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0007"
        page_dir.mkdir(parents=True, exist_ok=True)

        # Stale artifact: 56 unfiltered annotations (written first → older mtime)
        stale = {
            "schema_version": "1.0",
            "presentation_mode": "facsimile",
            "page": {"page_id": "p0007", "title": "Components"},
            "blocks": [],
            "facsimile": {
                "raster_src": "rasters/p0007__150dpi.png",
                "annotations": [{"text": f"a{i}", "bbox": {}} for i in range(56)],
            },
        }
        (page_dir / "hash_stale.json").write_text(json.dumps(stale))

        time.sleep(0.05)

        # Newer artifact: 31 quality-filtered annotations (written second → newer mtime)
        filtered = {
            "schema_version": "1.0",
            "presentation_mode": "facsimile",
            "page": {"page_id": "p0007", "title": "Components"},
            "blocks": [],
            "facsimile": {
                "raster_src": "rasters/p0007__150dpi.png",
                "annotations": [{"text": f"a{i}", "bbox": {}} for i in range(31)],
            },
        }
        (page_dir / "hash_filtered.json").write_text(json.dumps(filtered))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "ru", render_src, doc_public, {})

        exported = json.loads((doc_public / "ru" / "data" / "render_page.p0007.json").read_text())
        assert len(exported["facsimile"]["annotations"]) == 31
