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


class TestExportGlossary:
    """``export_glossary`` is now ref-bound (S5U-869): it takes the single
    glossary artifact path resolved from the exported run, not an mtime-glob
    over a directory. Selection lives in ``_export_run`` (see test_export_run).
    """

    def test_exports_resolved_glossary_payload(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """The explicitly-resolved glossary path is written verbatim to the bundle."""
        glossary_path = tmp_path / "glossary_payload.v1" / "ato_core_v1_1" / "abc123.json"
        glossary_path.parent.mkdir(parents=True)
        glossary_path.write_text(
            json.dumps(
                {
                    "schema_version": "glossary_payload.v1",
                    "entries": [{"id": f"c{i}"} for i in range(192)],
                }
            )
        )

        doc_public = tmp_path / "public" / "ato_core_v1_1"
        (doc_public / "en" / "data").mkdir(parents=True)

        export_module.export_glossary("ato_core_v1_1", "en", glossary_path, doc_public)

        exported = json.loads((doc_public / "en" / "data" / "glossary.json").read_text())
        assert len(exported["entries"]) == 192

    def test_none_path_skips_quietly(self, tmp_path: Path, export_module: ModuleType) -> None:
        """A run carrying no glossary ref (path=None) skips without writing."""
        doc_public = tmp_path / "public"
        (doc_public / "en" / "data").mkdir(parents=True)
        export_module.export_glossary("doc", "en", None, doc_public)
        assert not (doc_public / "en" / "data" / "glossary.json").exists()


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
    """``export_pages`` now receives ref-bound render-page payloads (S5U-869):
    a ``{page_id: page_data}`` dict already selected from one run. Selection is
    the run resolver's job (see test_export_run); these tests pin the
    transformation/navigation/manifest behaviour that ``export_pages`` owns.
    """

    def _make_pages(
        self,
        pages: list[str],
        has_cyrillic: bool = False,
        edition: str = "",
    ) -> dict[str, dict]:
        """Build a ref-bound ``{page_id: page_data}`` map for export_pages."""
        return {
            pid: _make_render_page(pid, has_cyrillic=has_cyrillic, edition=edition) for pid in pages
        }

    def test_en_edition_writes_to_edition_subdir(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        render_pages = self._make_pages(["p0001", "p0002"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

        assert (doc_public / "en" / "data" / "render_page.p0001.json").exists()
        assert (doc_public / "en" / "data" / "render_page.p0002.json").exists()
        assert (doc_public / "en" / "manifest.json").exists()
        # Root-level data dir should NOT exist
        assert not (doc_public / "data").exists()

    def test_ru_edition_writes_to_edition_subdir(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        render_pages = self._make_pages(["p0001"], has_cyrillic=True)
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "ru", render_pages, doc_public, {})

        assert (doc_public / "ru" / "data" / "render_page.p0001.json").exists()
        assert (doc_public / "ru" / "manifest.json").exists()

    def test_manifest_contains_page_list(self, tmp_path: Path, export_module: ModuleType) -> None:
        render_pages = self._make_pages(["p0001", "p0002"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert manifest["document_id"] == "doc1"
        page_ids = [p["page_id"] for p in manifest["pages"]]
        assert page_ids == ["p0001", "p0002"]

    def test_provenance_stamped_into_manifest(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """S5U-869: run provenance is stamped into the exported manifest."""
        render_pages = self._make_pages(["p0001"])
        doc_public = tmp_path / "web" / "documents" / "doc1"
        provenance = {
            "run_id": "run_abc123",
            "git_commit": "deadbeef",
            "edition": "en",
            "source_pdf_sha256": "f00d",
        }

        export_module.export_pages("doc1", "en", render_pages, doc_public, {}, provenance)

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert manifest["provenance"] == provenance

    def test_no_provenance_key_when_absent(self, tmp_path: Path, export_module: ModuleType) -> None:
        """Manifest omits the provenance key when none is supplied (legacy callers)."""
        render_pages = self._make_pages(["p0001"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert "provenance" not in manifest

    def test_both_editions_coexist(self, tmp_path: Path, export_module: ModuleType) -> None:
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", self._make_pages(["p0001"]), doc_public, {})
        export_module.export_pages(
            "doc1", "ru", self._make_pages(["p0001"], has_cyrillic=True), doc_public, {}
        )

        assert (doc_public / "en" / "manifest.json").exists()
        assert (doc_public / "ru" / "manifest.json").exists()

    def test_navigation_links(self, tmp_path: Path, export_module: ModuleType) -> None:
        render_pages = self._make_pages(["p0001", "p0002", "p0003"])
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

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
        render_pages = {
            "p0007": {
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
        }
        doc_public = tmp_path / "web" / "documents" / "doc1"

        # Pass image data — should NOT be injected for facsimile page
        images = {"p0007": [{"asset_id": "img0051", "src": "/img.png", "alt": "x"}]}
        export_module.export_pages("doc1", "en", render_pages, doc_public, images)

        exported = json.loads((doc_public / "en" / "data" / "render_page.p0007.json").read_text())
        assert exported["presentation_mode"] == "facsimile"
        # Raster URLs rewritten to web-public paths
        assert "/documents/doc1/rasters/" in exported["facsimile"]["raster_src"]
        # No synthetic figure blocks injected
        assert not any(b.get("asset_id") == "img0051" for b in exported.get("blocks", []))

    def test_empty_pages_excluded_from_manifest(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-431: pages with 0 blocks must not appear in the manifest."""
        render_pages = {
            "p0001": _make_render_page("p0001"),
            "p0002": _make_render_page("p0002", block_count=0),
            "p0003": _make_render_page("p0003"),
        }
        doc_public = tmp_path / "web" / "documents" / "doc1"
        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

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
        render_pages = {
            "p0007": {
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
        }
        doc_public = tmp_path / "web" / "documents" / "doc1"

        export_module.export_pages("doc1", "en", render_pages, doc_public, {})

        manifest = json.loads((doc_public / "en" / "manifest.json").read_text())
        assert [p["page_id"] for p in manifest["pages"]] == ["p0007"]
        assert (doc_public / "en" / "data" / "render_page.p0007.json").exists()

    def test_bare_figure_ids_rewritten_during_export(
        self, tmp_path: Path, export_module: ModuleType
    ) -> None:
        """Regression S5U-438: bare imgNNNN asset IDs must be namespaced during export."""
        render_pages = {
            "p0020": {
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
        }
        doc_public = tmp_path / "web" / "documents" / "doc1"

        # Pass namespaced page_images (simulates extract_images() output)
        page_images = {
            "p0020": [
                {
                    "asset_id": "p0020.img0000",
                    "src": "/documents/doc1/images/p0020.img0000.jpeg",
                    "alt": "p0020.img0000",
                }
            ]
        }
        export_module.export_pages("doc1", "en", render_pages, doc_public, page_images)

        exported = json.loads((doc_public / "en" / "data" / "render_page.p0020.json").read_text())
        # No bare imgNNNN keys should remain in figures
        for key in exported.get("figures", {}):
            assert not key.startswith("img"), f"Bare asset key '{key}' found in exported figures"
        # Figure blocks should have namespaced asset_id
        fig_blocks = [b for b in exported.get("blocks", []) if b.get("kind") == "figure"]
        for block in fig_blocks:
            assert "." in block["asset_id"], f"Bare asset_id in block: {block['asset_id']}"
        # Should have exactly one figure block (no duplicates from inject_image_figures)
        assert len(fig_blocks) == 1
        # The figure entry should have a valid src from page_images
        fig_entry = exported["figures"]["p0020.img0000"]
        assert fig_entry["src"] == "/documents/doc1/images/p0020.img0000.jpeg"


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


class TestRewriteFigureUrls:
    def test_rewrites_data_images_prefix(self, blocks_module: ModuleType) -> None:
        """Pipeline-relative data/images/ paths are rewritten to web-public paths."""
        page_data: dict = {
            "figures": {
                "p0067.img0000": {"src": "data/images/p0067.img0000.jpeg", "alt": "x"},
            },
        }
        count = blocks_module.rewrite_figure_urls(page_data, "ato_core_v1_1")
        assert count == 1
        assert page_data["figures"]["p0067.img0000"]["src"] == (
            "/documents/ato_core_v1_1/images/p0067.img0000.jpeg"
        )

    def test_skips_already_absolute_paths(self, blocks_module: ModuleType) -> None:
        """Paths already using /documents/ prefix are not touched."""
        page_data: dict = {
            "figures": {
                "p0065.img0000": {
                    "src": "/documents/ato_core_v1_1/images/p0065.img0000.jpeg",
                    "alt": "x",
                },
            },
        }
        count = blocks_module.rewrite_figure_urls(page_data, "ato_core_v1_1")
        assert count == 0

    def test_handles_empty_figures(self, blocks_module: ModuleType) -> None:
        """No error when figures dict is empty or missing."""
        assert blocks_module.rewrite_figure_urls({}, "doc") == 0
        assert blocks_module.rewrite_figure_urls({"figures": {}}, "doc") == 0


class TestInjectImageFiguresCap:
    def test_respects_max_figure_cap(self, blocks_module: ModuleType) -> None:
        """Image injection stops at _MAX_INJECTED_FIGURES."""
        page_data: dict = {"blocks": [], "figures": {}}
        imgs = [
            {"asset_id": f"p0075.img{i:04d}", "src": f"/img/{i}.png", "alt": f"img{i}"}
            for i in range(30)
        ]
        blocks_module.inject_image_figures(page_data, "p0075", imgs)
        fig_blocks = [b for b in page_data["blocks"] if b["kind"] == "figure"]
        assert len(fig_blocks) == blocks_module._MAX_INJECTED_FIGURES

    def test_existing_figures_count_against_cap(self, blocks_module: ModuleType) -> None:
        """Pre-existing figure blocks reduce the injection budget."""
        existing = [
            {"kind": "figure", "id": f"p0075.b{i}", "asset_id": f"p0075.existing{i}"}
            for i in range(15)
        ]
        page_data: dict = {"blocks": list(existing), "figures": {}}
        imgs = [
            {"asset_id": f"p0075.img{i:04d}", "src": f"/img/{i}.png", "alt": f"img{i}"}
            for i in range(30)
        ]
        blocks_module.inject_image_figures(page_data, "p0075", imgs)
        fig_blocks = [b for b in page_data["blocks"] if b["kind"] == "figure"]
        assert len(fig_blocks) == blocks_module._MAX_INJECTED_FIGURES

    def test_already_referenced_images_update_src(self, blocks_module: ModuleType) -> None:
        """Images already in blocks get src updated without counting against cap."""
        page_data: dict = {
            "blocks": [
                {"kind": "figure", "id": "p.b0", "asset_id": "p.img0000", "children": []},
            ],
            "figures": {"p.img0000": {"src": "old", "alt": "old"}},
        }
        imgs = [{"asset_id": "p.img0000", "src": "/new.png", "alt": "new"}]
        blocks_module.inject_image_figures(page_data, "p", imgs)
        assert page_data["figures"]["p.img0000"]["src"] == "/new.png"
        assert len(page_data["blocks"]) == 1  # no new block added
