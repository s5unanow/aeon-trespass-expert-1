"""Tests for render payload builders."""

from pathlib import Path

from atr_pipeline.stages.glossary.registry_loader import load_concept_registry
from atr_pipeline.stages.render.glossary_builder import build_glossary_payload
from atr_pipeline.stages.render.nav_builder import build_nav_payload
from atr_pipeline.stages.render.page_builder import build_render_page
from atr_pipeline.stages.render.search_builder import build_search_docs
from atr_schemas.common import Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    FigureBlock,
    HeadingBlock,
    IconInline,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _make_ru_ir() -> PageIRV1:
    return PageIRV1(
        document_id="walking_skeleton",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0001.b001",
                level=2,
                children=[TextInline(text="Проверка атаки", lang=LanguageCode.RU)],
            ),
            ParagraphBlock(
                block_id="p0001.b002",
                children=[
                    TextInline(text="Получите 1 ", lang=LanguageCode.RU),
                    IconInline(symbol_id="sym.progress", instance_id="syminst.p0001.01"),
                    TextInline(text=" Прогресс.", lang=LanguageCode.RU),
                ],
            ),
        ],
        reading_order=["p0001.b001", "p0001.b002"],
    )


def test_render_page_builder() -> None:
    """Build a render page from Russian IR."""
    ir = _make_ru_ir()
    render = build_render_page(ir)

    assert render.page.title == "Проверка атаки"
    assert render.page.source_page_number == 1
    assert len(render.blocks) == 2
    assert "concept.progress" in render.glossary_mentions


def test_glossary_builder() -> None:
    """Build glossary payload from concept registry."""
    ir = _make_ru_ir()
    render = build_render_page(ir)
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")

    glossary = build_glossary_payload("walking_skeleton", registry, [render])

    # All registry concepts are included, not just mentioned ones
    assert len(glossary.entries) == len(registry.concepts)
    by_id = {e.concept_id: e for e in glossary.entries}
    # Mentioned concept has page_refs
    progress = by_id["concept.progress"]
    assert progress.preferred_term == "Прогресс"
    assert progress.icon_binding == "sym.progress"
    assert len(progress.page_refs) == 1
    assert progress.page_refs[0].page_id == "p0001"
    assert progress.page_refs[0].source_page_number == 1
    # Unmentioned concept is still present but with empty page_refs
    triskelion = by_id["concept.triskelion"]
    assert triskelion.preferred_term == "Трискелион"
    assert triskelion.page_refs == []


def test_search_builder() -> None:
    """Build search docs from render page."""
    ir = _make_ru_ir()
    render = build_render_page(ir)

    search = build_search_docs("walking_skeleton", [render])

    assert len(search.docs) == 1
    doc = search.docs[0]
    assert doc.page_id == "p0001"
    assert "Проверка" in doc.text
    assert len(doc.normalized_terms) > 0


def test_nav_builder() -> None:
    """Build nav payload from render pages."""
    ir = _make_ru_ir()
    render = build_render_page(ir)

    nav = build_nav_payload("walking_skeleton", [render])

    assert nav.document_id == "walking_skeleton"
    assert len(nav.pages) == 1
    assert nav.pages[0].page_id == "p0001"


def test_text_based_concept_mentions() -> None:
    """Text-only concepts are detected from TextInline content."""
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0010",
        page_number=10,
        language=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0010.b001",
                level=2,
                children=[TextInline(text="Фаза путешествия", lang=LanguageCode.RU)],
            ),
            ParagraphBlock(
                block_id="p0010.b002",
                children=[
                    TextInline(
                        text="During the Voyage Phase heroes travel.",
                        lang=LanguageCode.EN,
                    ),
                ],
            ),
        ],
        reading_order=["p0010.b001", "p0010.b002"],
    )
    render = build_render_page(ir, concept_registry=registry)
    assert "concept.voyage_phase" in render.glossary_mentions


def test_text_and_icon_concept_mentions_no_duplicates() -> None:
    """Icon and text both referring to same concept produce no duplicates."""
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0011",
        page_number=11,
        language=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="p0011.b001",
                children=[
                    TextInline(text="Получите 1 ", lang=LanguageCode.RU),
                    IconInline(symbol_id="sym.progress", instance_id="syminst.p0011.01"),
                    TextInline(text=" Прогресс.", lang=LanguageCode.RU),
                ],
            ),
        ],
        reading_order=["p0011.b001"],
    )
    render = build_render_page(ir, concept_registry=registry)
    # Icon detected it first; text should not duplicate
    progress_count = render.glossary_mentions.count("concept.progress")
    assert progress_count == 1


def test_russian_surface_form_detection() -> None:
    """Russian allowed_surface_forms are detected in text nodes."""
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0012",
        page_number=12,
        language=LanguageCode.RU,
        blocks=[
            ParagraphBlock(
                block_id="p0012.b001",
                children=[
                    TextInline(text="Начинается Фаза Странствия.", lang=LanguageCode.RU),
                ],
            ),
        ],
        reading_order=["p0012.b001"],
    )
    render = build_render_page(ir, concept_registry=registry)
    assert "concept.voyage_phase" in render.glossary_mentions


def test_text_concept_mentions_without_registry() -> None:
    """Without a registry, only icon-based detection works (backward compat)."""
    ir = _make_ru_ir()
    render = build_render_page(ir)
    # Icon-based: concept.progress is found
    assert "concept.progress" in render.glossary_mentions
    # Text "Прогресс" is in the IR but no registry → not double-counted
    assert render.glossary_mentions.count("concept.progress") == 1


def test_concept_registry_loader() -> None:
    """Load concept registry from TOML."""
    registry = load_concept_registry(_repo_root() / "configs" / "glossary" / "concepts.toml")

    assert len(registry.concepts) >= 9  # stat icons + game terms
    # Verify a known concept loads correctly
    by_id = {c.concept_id: c for c in registry.concepts}
    c = by_id["concept.progress"]
    assert c.source.lemma == "Progress"
    assert c.target.lemma == "Прогресс"
    assert c.icon_binding == "sym.progress"
    assert "Продвижение" in c.forbidden_targets
    # Verify Triskelion stats are present
    assert "concept.danger" in by_id
    assert "concept.fate" in by_id
    assert "concept.rage" in by_id


def test_render_page_builder_list_items() -> None:
    """List item blocks are rendered as list_item render blocks."""
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0002",
        page_number=2,
        language=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id="p0002.b001",
                level=2,
                children=[TextInline(text="Список", lang=LanguageCode.RU)],
            ),
            ListItemBlock(
                block_id="p0002.b002",
                children=[TextInline(text="Первый пункт", lang=LanguageCode.RU)],
            ),
            ListItemBlock(
                block_id="p0002.b003",
                children=[TextInline(text="Второй пункт", lang=LanguageCode.RU)],
            ),
        ],
        reading_order=["p0002.b001", "p0002.b002", "p0002.b003"],
    )
    render = build_render_page(ir)

    assert len(render.blocks) == 3
    assert render.blocks[0].kind == "heading"
    assert render.blocks[1].kind == "list_item"
    assert render.blocks[2].kind == "list_item"
    # Verify children were converted
    li_block = render.blocks[1]
    assert len(li_block.children) == 1  # type: ignore[union-attr]
    assert li_block.children[0].kind == "text"  # type: ignore[union-attr]


def test_render_page_builder_figure_blocks() -> None:
    """FigureBlock in IR produces a figure render block and populates figures dict."""
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0003",
        page_number=3,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="p0003.b001",
                level=1,
                children=[TextInline(text="Chapter with Image", lang=LanguageCode.EN)],
            ),
            FigureBlock(
                block_id="p0003.b002",
                asset_id="img0000",
                bbox=Rect(x0=50, y0=100, x1=400, y1=350),
                translatable=False,
            ),
        ],
        assets=["img0000"],
        reading_order=["p0003.b001", "p0003.b002"],
    )
    render = build_render_page(ir, image_base_path="/documents/test_doc/images")

    assert len(render.blocks) == 2
    assert render.blocks[0].kind == "heading"
    assert render.blocks[1].kind == "figure"

    fig_block = render.blocks[1]
    assert fig_block.asset_id == "img0000"  # type: ignore[union-attr]

    # The figures dict should contain the asset reference
    assert "img0000" in render.figures
    fig = render.figures["img0000"]
    assert fig.src == "/documents/test_doc/images/img0000"
    assert fig.alt == "img0000"


def test_render_page_builder_figure_no_base_path() -> None:
    """Without image_base_path, figure src falls back to asset_id."""
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0004",
        page_number=4,
        language=LanguageCode.EN,
        blocks=[
            FigureBlock(
                block_id="p0004.b001",
                asset_id="img0001",
                translatable=False,
            ),
        ],
        assets=["img0001"],
        reading_order=["p0004.b001"],
    )
    render = build_render_page(ir)

    assert "img0001" in render.figures
    assert render.figures["img0001"].src == "img0001"


def test_render_page_builder_figure_image_sources() -> None:
    """image_sources overrides image_base_path for figure src."""
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0005",
        page_number=5,
        language=LanguageCode.EN,
        blocks=[
            FigureBlock(
                block_id="p0005.b001",
                asset_id="img0001",
                translatable=False,
            ),
        ],
        assets=["img0001"],
        reading_order=["p0005.b001"],
    )
    sources = {"img0001": "data/images/img0001.png"}
    render = build_render_page(ir, image_base_path="/fallback", image_sources=sources)

    assert render.figures["img0001"].src == "data/images/img0001.png"


def test_inject_nav_populates_prev_next() -> None:
    """RenderStage._inject_nav sets prev/next on each page."""
    from atr_pipeline.stages.render.stage import RenderStage

    pages = [
        build_render_page(_make_ir(page_id="p0001", page_number=1)),
        build_render_page(_make_ir(page_id="p0002", page_number=2)),
        build_render_page(_make_ir(page_id="p0003", page_number=3)),
    ]
    RenderStage._inject_nav(pages)

    assert pages[0].nav.prev is None
    assert pages[0].nav.next == "p0002"
    assert pages[1].nav.prev == "p0001"
    assert pages[1].nav.next == "p0003"
    assert pages[2].nav.prev == "p0002"
    assert pages[2].nav.next is None


def test_resolve_images_finds_image_files(tmp_path: Path) -> None:
    """_resolve_images returns sources and refs from the image artifact dir."""
    from unittest.mock import MagicMock

    from atr_pipeline.stages.render.stage import RenderStage
    from atr_pipeline.store.artifact_store import ArtifactStore

    store = ArtifactStore(tmp_path / "artifacts")

    # Create image files in the expected structure
    img_dir = store.root / "doc1" / "image" / "page" / "p0001.img0000"
    img_dir.mkdir(parents=True)
    (img_dir / "abc123.png").write_bytes(b"fake png")

    img_dir2 = store.root / "doc1" / "image" / "page" / "p0001.img0001"
    img_dir2.mkdir(parents=True)
    (img_dir2 / "def456.jpeg").write_bytes(b"fake jpeg")

    # Create a non-image file that should be ignored
    (img_dir / ".DS_Store").write_bytes(b"junk")

    ctx = MagicMock()
    ctx.artifact_store = store
    ctx.document_id = "doc1"

    sources, refs = RenderStage._resolve_images(ctx)

    assert sources["p0001.img0000"] == "data/images/p0001.img0000.png"
    assert sources["p0001.img0001"] == "data/images/p0001.img0001.jpeg"
    assert refs["p0001.img0000"].endswith("abc123.png")
    assert refs["p0001.img0001"].endswith("def456.jpeg")


def test_facsimile_page_gets_mode_and_metadata() -> None:
    """Facsimile pages get presentation_mode set and facsimile populated."""
    from atr_pipeline.stages.render.stage import _build_facsimile
    from atr_schemas.raster_meta_v1 import RasterLevel, RasterMetaV1

    meta = RasterMetaV1(
        document_id="doc1",
        page_id="p0007",
        page_number=7,
        source_pdf_sha256="abc",
        levels=[
            RasterLevel(
                dpi=150, width_px=1240, height_px=1754, content_hash="h1", relative_path="r1"
            ),
            RasterLevel(
                dpi=300, width_px=2480, height_px=3508, content_hash="h2", relative_path="r2"
            ),
        ],
    )
    fac = _build_facsimile(meta)
    assert fac.raster_src == "rasters/p0007__150dpi.png"
    assert fac.raster_src_hires == "rasters/p0007__300dpi.png"
    assert fac.width_px == 1240
    assert fac.height_px == 1754


def test_title_override_applied() -> None:
    """Title override replaces auto-derived title."""
    from atr_pipeline.config.models import PageOverride

    ir = _make_ir(page_id="p0007", page_number=7)
    render = build_render_page(ir)
    assert render.page.title == "Page 7"  # auto-derived from heading

    override = PageOverride(title="Components")
    render.page.title = override.title or render.page.title
    assert render.page.title == "Components"


def test_facsimile_fallback_title_for_short_garbage() -> None:
    """Facsimile pages with very short titles get fallback 'Page N'."""
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0007",
        page_number=7,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id="p0007.b001",
                level=1,
                children=[TextInline(text="I", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=["p0007.b001"],
    )
    render = build_render_page(ir)
    assert render.page.title == "I"
    # Simulate the stage logic for facsimile fallback
    if len(render.page.title) <= 2:
        render.page.title = f"Page {ir.page_number}"
    assert render.page.title == "Page 7"


def _make_ir(*, page_id: str, page_number: int) -> PageIRV1:
    return PageIRV1(
        document_id="test_doc",
        page_id=page_id,
        page_number=page_number,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id=f"{page_id}.b001",
                level=1,
                children=[TextInline(text=f"Page {page_number}", lang=LanguageCode.EN)],
            ),
        ],
        reading_order=[f"{page_id}.b001"],
    )
