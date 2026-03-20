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

    assert len(glossary.entries) == 1
    assert glossary.entries[0].concept_id == "concept.progress"
    assert glossary.entries[0].preferred_term == "Прогресс"
    assert glossary.entries[0].icon_binding == "sym.progress"


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
