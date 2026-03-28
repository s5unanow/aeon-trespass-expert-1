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
SCRIPTS_DIR = REPO / "scripts"


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


@pytest.fixture()
def blocks_module() -> Iterator[ModuleType]:
    """Import _export_blocks.py as a module."""
    blocks_path = SCRIPTS_DIR / "_export_blocks.py"
    spec = importlib.util.spec_from_file_location("_export_blocks", blocks_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_export_blocks_test"] = mod
    spec.loader.exec_module(mod)
    yield mod
    sys.modules.pop("_export_blocks_test", None)


def _make_render_page(
    page_id: str,
    has_cyrillic: bool = False,
    has_marks: bool = False,
    block_count: int = 3,
    edition: str = "",
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
        "document_version": edition,
        "page": {"page_id": page_id, "title": f"Page {page_id}"},
        "blocks": blocks,
    }


class TestPickLatest:
    def test_picks_most_recently_modified(self, tmp_path: Path, export_module: ModuleType) -> None:
        """The newest file by mtime wins, regardless of content."""
        import os

        old = tmp_path / "old.json"
        old.write_text('{"v": "old"}')
        os.utime(old, (1_000_000, 1_000_000))

        new = tmp_path / "new.json"
        new.write_text('{"v": "new"}')
        os.utime(new, (2_000_000, 2_000_000))

        result = export_module._pick_latest([old, new])
        assert result == {"v": "new"}

    def test_newer_filtered_facsimile_beats_stale_unfiltered(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression: newer quality-filtered artifact must beat stale one with more annotations."""
        import os

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
        os.utime(stale, (1_000_000, 1_000_000))

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
        os.utime(filtered, (2_000_000, 2_000_000))

        result = export_module._pick_latest([stale, filtered])
        assert result is not None
        assert len(result["facsimile"]["annotations"]) == 31

    def test_filters_by_edition(self, tmp_path: Path, export_module: ModuleType) -> None:
        """Only artifacts whose document_version matches the edition are selected."""
        import os

        en_artifact = tmp_path / "en.json"
        en_artifact.write_text(json.dumps({"document_version": "en", "lang": "en"}))
        os.utime(en_artifact, (1_000_000, 1_000_000))

        ru_artifact = tmp_path / "ru.json"
        ru_artifact.write_text(json.dumps({"document_version": "ru", "lang": "ru"}))
        os.utime(ru_artifact, (2_000_000, 2_000_000))

        # Requesting EN should pick the EN artifact even though RU is newer
        result = export_module._pick_latest([en_artifact, ru_artifact], "en")
        assert result is not None
        assert result["document_version"] == "en"

        # Requesting RU should pick the RU artifact
        result = export_module._pick_latest([en_artifact, ru_artifact], "ru")
        assert result is not None
        assert result["document_version"] == "ru"

    def test_empty_document_version_matches_when_no_tagged_artifacts(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Pre-S5U-402 artifacts with empty document_version match any edition
        when no tagged artifacts exist for the page."""
        import os

        legacy = tmp_path / "legacy.json"
        legacy.write_text(json.dumps({"document_version": "", "data": "ok"}))
        os.utime(legacy, (1_000_000, 1_000_000))

        result = export_module._pick_latest([legacy], "en")
        assert result is not None
        assert result["data"] == "ok"

    def test_untagged_rejected_when_tagged_artifact_exists(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-437: untagged artifacts must not match an edition
        when a tagged artifact for a *different* edition exists — the tag
        proves the page has edition-specific content."""
        import os

        # Untagged artifact (older — from before edition tagging)
        untagged = tmp_path / "legacy.json"
        untagged.write_text(json.dumps({"document_version": "", "data": "stale-ru-content"}))
        os.utime(untagged, (1_000_000, 1_000_000))

        # Tagged RU artifact (newer)
        tagged_ru = tmp_path / "tagged_ru.json"
        tagged_ru.write_text(json.dumps({"document_version": "ru", "data": "ru-content"}))
        os.utime(tagged_ru, (2_000_000, 2_000_000))

        # EN request: exact match absent, untagged fallback blocked by tag
        result = export_module._pick_latest([untagged, tagged_ru], "en")
        assert result is None

        # RU request: exact match found
        result = export_module._pick_latest([untagged, tagged_ru], "ru")
        assert result is not None
        assert result["document_version"] == "ru"

    def test_no_matching_edition_returns_none(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """When no artifact matches the edition, return None."""
        import os

        ru_only = tmp_path / "ru.json"
        ru_only.write_text(json.dumps({"document_version": "ru"}))
        os.utime(ru_only, (1_000_000, 1_000_000))

        result = export_module._pick_latest([ru_only], "en")
        assert result is None


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
        self,
        tmp_path: Path,
        doc_id: str,
        pages: list[str],
        has_cyrillic: bool = False,
        edition: str = "",
    ) -> Path:
        """Create fake render artifacts and return the render_src path."""
        render_src = tmp_path / "artifacts" / doc_id / "render_page.v1" / "page"
        for pid in pages:
            page_dir = render_src / pid
            page_dir.mkdir(parents=True, exist_ok=True)
            data = _make_render_page(pid, has_cyrillic=has_cyrillic, edition=edition)
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
        import os

        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0007"
        page_dir.mkdir(parents=True, exist_ok=True)

        # Stale artifact: 56 unfiltered annotations (older mtime)
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
        stale_path = page_dir / "hash_stale.json"
        stale_path.write_text(json.dumps(stale))
        os.utime(stale_path, (1_000_000, 1_000_000))

        # Newer artifact: 31 quality-filtered annotations (newer mtime)
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
        filtered_path = page_dir / "hash_filtered.json"
        filtered_path.write_text(json.dumps(filtered))
        os.utime(filtered_path, (2_000_000, 2_000_000))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "ru", render_src, doc_public, {})

        exported = json.loads((doc_public / "ru" / "data" / "render_page.p0007.json").read_text())
        assert len(exported["facsimile"]["annotations"]) == 31

    def test_edition_filter_skips_wrong_language(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-402: exporting --edition=en must not pick a RU artifact."""
        import os

        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0001"
        page_dir.mkdir(parents=True, exist_ok=True)

        # EN artifact (older)
        en_data = _make_render_page("p0001", edition="en")
        en_path = page_dir / "hash_en.json"
        en_path.write_text(json.dumps(en_data))
        os.utime(en_path, (1_000_000, 1_000_000))

        # RU artifact (newer — would win without edition filtering)
        ru_data = _make_render_page("p0001", has_cyrillic=True, edition="ru")
        ru_path = page_dir / "hash_ru.json"
        ru_path.write_text(json.dumps(ru_data))
        os.utime(ru_path, (2_000_000, 2_000_000))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        exported = json.loads((doc_public / "en" / "data" / "render_page.p0001.json").read_text())
        # Must contain English text, not Russian
        block_text = exported["blocks"][0]["children"][0]["text"]
        assert block_text == "Example text"

    def test_empty_pages_excluded_from_manifest(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-431: pages with 0 blocks must not appear in the manifest."""
        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"

        # p0001: normal page with blocks
        p1_dir = render_src / "p0001"
        p1_dir.mkdir(parents=True, exist_ok=True)
        (p1_dir / "h1.json").write_text(json.dumps(_make_render_page("p0001")))

        # p0002: empty page (0 blocks, like a blank cover)
        p2_dir = render_src / "p0002"
        p2_dir.mkdir(parents=True, exist_ok=True)
        (p2_dir / "h2.json").write_text(json.dumps(_make_render_page("p0002", block_count=0)))

        # p0003: normal page with blocks
        p3_dir = render_src / "p0003"
        p3_dir.mkdir(parents=True, exist_ok=True)
        (p3_dir / "h3.json").write_text(json.dumps(_make_render_page("p0003")))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        page_ids = [p["page_id"] for p in manifest["pages"]]
        assert "p0002" not in page_ids
        assert page_ids == ["p0001", "p0003"]

        # No render artifact written for empty page
        assert not (doc_public / "en" / "data" / "render_page.p0002.json").exists()

        # Navigation skips the empty page
        p1 = json.loads((doc_public / "en" / "data" / "render_page.p0001.json").read_text())
        assert p1["nav"]["next"] == "p0003"
        p3 = json.loads((doc_public / "en" / "data" / "render_page.p0003.json").read_text())
        assert p3["nav"]["prev"] == "p0001"

    def test_empty_facsimile_pages_still_exported(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Facsimile pages with 0 blocks are valid — content is the raster image."""
        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0007"
        page_dir.mkdir(parents=True, exist_ok=True)
        facsimile_page = {
            "schema_version": "1.0",
            "presentation_mode": "facsimile",
            "document_version": "",
            "page": {"page_id": "p0007", "title": "Components"},
            "blocks": [],
            "facsimile": {
                "raster_src": "rasters/p0007__150dpi.png",
                "raster_src_hires": "rasters/p0007__300dpi.png",
            },
        }
        (page_dir / "h1.json").write_text(json.dumps(facsimile_page))
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert [p["page_id"] for p in manifest["pages"]] == ["p0007"]
        assert (doc_public / "en" / "data" / "render_page.p0007.json").exists()

    def test_nav_links_skip_filtered_pages(self, tmp_path: Path, export_module: ModuleType) -> None:
        """Navigation links reference only pages that were actually exported."""
        import os

        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"

        # p0001: EN only
        p1_dir = render_src / "p0001"
        p1_dir.mkdir(parents=True, exist_ok=True)
        p1 = p1_dir / "h1.json"
        p1.write_text(json.dumps(_make_render_page("p0001", edition="en")))
        os.utime(p1, (1_000_000, 1_000_000))

        # p0002: RU only (no EN artifact — should be skipped for EN export)
        p2_dir = render_src / "p0002"
        p2_dir.mkdir(parents=True, exist_ok=True)
        p2 = p2_dir / "h2.json"
        p2.write_text(json.dumps(_make_render_page("p0002", has_cyrillic=True, edition="ru")))
        os.utime(p2, (1_000_000, 1_000_000))

        # p0003: EN only
        p3_dir = render_src / "p0003"
        p3_dir.mkdir(parents=True, exist_ok=True)
        p3 = p3_dir / "h3.json"
        p3.write_text(json.dumps(_make_render_page("p0003", edition="en")))
        os.utime(p3, (1_000_000, 1_000_000))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        # p0002 should not be exported
        assert not (doc_public / "en" / "data" / "render_page.p0002.json").exists()

        # p0001 → next should be p0003 (skipping p0002)
        e1 = json.loads((doc_public / "en" / "data" / "render_page.p0001.json").read_text())
        assert e1["nav"]["prev"] is None
        assert e1["nav"]["next"] == "p0003"

        # p0003 → prev should be p0001 (skipping p0002)
        e3 = json.loads((doc_public / "en" / "data" / "render_page.p0003.json").read_text())
        assert e3["nav"]["prev"] == "p0001"
        assert e3["nav"]["next"] is None

    def test_bare_figure_ids_rewritten_during_export(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-438: bare imgNNNN asset IDs must be namespaced during export."""
        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0020"
        page_dir.mkdir(parents=True, exist_ok=True)
        page_data = {
            "schema_version": "1.0",
            "document_version": "",
            "page": {"page_id": "p0020", "title": "Test page"},
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "img0000", "children": []},
                {
                    "kind": "paragraph",
                    "id": "p0020.b001",
                    "children": [{"kind": "text", "text": "Some text"}],
                },
            ],
            "figures": {
                "img0000": {"src": "img0000", "alt": "img0000"},
            },
        }
        (page_dir / "hash_001.json").write_text(json.dumps(page_data))
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        exported = json.loads((doc_public / "en" / "data" / "render_page.p0020.json").read_text())
        # No bare imgNNNN keys should remain in figures
        for key in exported.get("figures", {}):
            assert not key.startswith("img"), f"Bare asset key '{key}' found in exported figures"
        # Figure blocks should have namespaced asset_id
        for block in exported.get("blocks", []):
            if block.get("kind") == "figure":
                assert "." in block["asset_id"], f"Bare asset_id in block: {block['asset_id']}"

    def test_untagged_facsimile_excluded_when_tagged_ru_exists(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-437: EN export must not pick an untagged facsimile
        that contains RU content when a tagged RU facsimile also exists."""
        import os

        render_src = tmp_path / "artifacts" / "doc1" / "render_page.v1" / "page"
        page_dir = render_src / "p0007"
        page_dir.mkdir(parents=True, exist_ok=True)

        # Untagged facsimile with RU content (pre-S5U-402)
        untagged = {
            "schema_version": "1.0",
            "presentation_mode": "facsimile",
            "document_version": "",
            "page": {"page_id": "p0007", "title": "Components"},
            "blocks": [
                {
                    "kind": "paragraph",
                    "id": "p0007.b1",
                    "children": [{"kind": "text", "text": "Пример"}],
                }
            ],
            "facsimile": {"raster_src": "rasters/p0007__150dpi.png"},
        }
        up = page_dir / "hash_old.json"
        up.write_text(json.dumps(untagged))
        os.utime(up, (1_000_000, 1_000_000))

        # Tagged RU facsimile (newer)
        tagged_ru = {
            **untagged,
            "document_version": "ru",
        }
        rp = page_dir / "hash_ru.json"
        rp.write_text(json.dumps(tagged_ru))
        os.utime(rp, (2_000_000, 2_000_000))

        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "en", render_src, doc_public, {})

        # p0007 must NOT appear in EN export
        assert not (doc_public / "en" / "data" / "render_page.p0007.json").exists()
        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert all(p["page_id"] != "p0007" for p in manifest["pages"])

        # RU export should still work
        export_module.export_pages("doc1", "ru", render_src, doc_public, {})
        assert (doc_public / "ru" / "data" / "render_page.p0007.json").exists()


class TestNamespaceBareFigures:
    def test_rewrites_bare_keys_in_figures_dict(self, blocks_module: ModuleType) -> None:
        """Bare imgNNNN keys are namespaced with page id."""
        page_data: dict = {
            "figures": {
                "img0000": {"src": "img0000", "alt": "img0000"},
            },
            "blocks": [],
        }
        count = blocks_module.namespace_bare_figures(page_data, "p0020")
        assert count == 1
        assert "img0000" not in page_data["figures"]
        assert "p0020.img0000" in page_data["figures"]

    def test_clears_bare_self_referencing_src(self, blocks_module: ModuleType) -> None:
        """When src is a bare self-reference, it's cleared."""
        page_data: dict = {
            "figures": {
                "img0001": {"src": "img0001", "alt": "img0001"},
            },
            "blocks": [],
        }
        blocks_module.namespace_bare_figures(page_data, "p0060")
        assert page_data["figures"]["p0060.img0001"]["src"] == ""

    def test_preserves_namespaced_when_both_exist(self, blocks_module: ModuleType) -> None:
        """When both bare and namespaced exist, namespaced is kept."""
        page_data: dict = {
            "figures": {
                "img0000": {"src": "img0000", "alt": "img0000"},
                "p0020.img0000": {"src": "/documents/doc/images/p0020.img0000.jpeg", "alt": "x"},
            },
            "blocks": [],
        }
        blocks_module.namespace_bare_figures(page_data, "p0020")
        assert "img0000" not in page_data["figures"]
        assert page_data["figures"]["p0020.img0000"]["src"] == (
            "/documents/doc/images/p0020.img0000.jpeg"
        )

    def test_rewrites_bare_asset_id_in_figure_blocks(self, blocks_module: ModuleType) -> None:
        """Figure blocks with bare asset_id get namespaced."""
        page_data: dict = {
            "figures": {},
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "img0000", "children": []},
            ],
        }
        count = blocks_module.namespace_bare_figures(page_data, "p0020")
        assert count == 1
        assert page_data["blocks"][0]["asset_id"] == "p0020.img0000"

    def test_noop_for_already_namespaced(self, blocks_module: ModuleType) -> None:
        """Already-namespaced entries are not touched."""
        page_data: dict = {
            "figures": {
                "p0020.img0000": {"src": "/documents/doc/images/p0020.img0000.jpeg", "alt": "x"},
            },
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "p0020.img0000", "children": []},
            ],
        }
        count = blocks_module.namespace_bare_figures(page_data, "p0020")
        assert count == 0


class TestValidateFigureRefs:
    def test_valid_figure_refs_pass(self, blocks_module: ModuleType) -> None:
        """Valid figure references produce no errors."""
        page_data: dict = {
            "figures": {
                "p0020.img0000": {"src": "/documents/doc/images/p0020.img0000.jpeg", "alt": "x"},
            },
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "p0020.img0000", "children": []},
            ],
        }
        errors = blocks_module.validate_figure_refs(page_data, "p0020")
        assert errors == []

    def test_missing_figure_entry_reported(self, blocks_module: ModuleType) -> None:
        """Figure block referencing a missing asset produces an error."""
        page_data: dict = {
            "figures": {},
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "p0020.img0000", "children": []},
            ],
        }
        errors = blocks_module.validate_figure_refs(page_data, "p0020")
        assert len(errors) == 1
        assert "missing asset" in errors[0]

    def test_bare_src_reported(self, blocks_module: ModuleType) -> None:
        """Figure with bare src value produces an error."""
        page_data: dict = {
            "figures": {"img0000": {"src": "img0000", "alt": "img0000"}},
            "blocks": [
                {"kind": "figure", "id": "p0020.b002", "asset_id": "img0000", "children": []},
            ],
        }
        errors = blocks_module.validate_figure_refs(page_data, "p0020")
        assert len(errors) == 1
        assert "bare src" in errors[0]
