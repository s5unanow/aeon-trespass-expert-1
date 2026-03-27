"""Tests for the semantic chunker module."""

from __future__ import annotations

from collections.abc import Sequence

from atr_pipeline.stages.assistant.chunker import (
    _canonical_anchor,
    _extract_text,
    _normalize_text,
    chunk_page,
)
from atr_schemas.common import PageDimensions, Rect
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    DividerBlock,
    HeadingBlock,
    IconInline,
    ListItemBlock,
    PageIRV1,
    ParagraphBlock,
    SectionHint,
    TableBlock,
    TermMarkInline,
    TextInline,
)


def _make_page(
    blocks: Sequence[Block],
    reading_order: list[str] | None = None,
    page_id: str = "p0001",
    page_number: int = 1,
    language: LanguageCode = LanguageCode.EN,
    section_hint: SectionHint | None = None,
    dimensions: PageDimensions | None = None,
) -> PageIRV1:
    if reading_order is None:
        reading_order = [b.block_id for b in blocks]
    return PageIRV1(
        document_id="test_doc",
        page_id=page_id,
        page_number=page_number,
        language=language,
        blocks=list(blocks),
        reading_order=reading_order,
        section_hint=section_hint,
        dimensions_pt=dimensions,
    )


def _para(bid: str, text: str) -> ParagraphBlock:
    return ParagraphBlock(
        block_id=bid,
        children=[TextInline(text=text)],
    )


def _heading(bid: str, text: str, level: int = 1) -> HeadingBlock:
    return HeadingBlock(
        block_id=bid,
        level=level,
        children=[TextInline(text=text)],
    )


# --- chunk_page tests ---


def test_single_paragraph_produces_one_chunk() -> None:
    page = _make_page([_para("p0001.b001", "Some rule text.")])
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 1
    assert chunks[0].text == "Some rule text."
    assert chunks[0].block_ids == ["p0001.b001"]
    assert chunks[0].language == LanguageCode.EN


def test_heading_plus_paragraphs_merged() -> None:
    """Heading + up to 3 following paragraphs form one chunk."""
    blocks: list[Block] = [
        _heading("p0001.b001", "Section Title"),
        _para("p0001.b002", "First paragraph."),
        _para("p0001.b003", "Second paragraph."),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 1
    assert chunks[0].block_ids == ["p0001.b001", "p0001.b002", "p0001.b003"]
    assert "Section Title" in chunks[0].text
    assert "First paragraph." in chunks[0].text


def test_heading_group_splits_after_max_paragraphs() -> None:
    """After 3 paragraphs, the 4th starts a new standalone chunk."""
    blocks: list[Block] = [
        _heading("p0001.b001", "Title"),
        _para("p0001.b002", "P1"),
        _para("p0001.b003", "P2"),
        _para("p0001.b004", "P3"),
        _para("p0001.b005", "P4 should be separate"),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 2
    assert chunks[0].block_ids == ["p0001.b001", "p0001.b002", "p0001.b003", "p0001.b004"]
    assert chunks[1].block_ids == ["p0001.b005"]


def test_callout_is_standalone() -> None:
    blocks: list[Block] = [
        _para("p0001.b001", "Before callout."),
        CalloutBlock(block_id="p0001.b002", children=[TextInline(text="Warning!")]),
        _para("p0001.b003", "After callout."),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 3
    assert chunks[1].text == "Warning!"
    assert chunks[1].block_ids == ["p0001.b002"]


def test_table_is_standalone() -> None:
    blocks: list[Block] = [
        _para("p0001.b001", "Before table."),
        TableBlock(block_id="p0001.b002", children=[TextInline(text="Col1 Col2")]),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 2
    assert chunks[1].block_ids == ["p0001.b002"]


def test_list_item_is_standalone() -> None:
    blocks = [
        ListItemBlock(block_id="p0001.b001", children=[TextInline(text="Item 1")]),
        ListItemBlock(block_id="p0001.b002", children=[TextInline(text="Item 2")]),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 2


def test_divider_splits_groups() -> None:
    """Dividers break heading groups without producing a chunk."""
    blocks: list[Block] = [
        _heading("p0001.b001", "Title"),
        DividerBlock(block_id="p0001.b002"),
        _para("p0001.b003", "After divider."),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 2
    assert chunks[0].block_ids == ["p0001.b001"]
    assert chunks[1].block_ids == ["p0001.b003"]


def test_empty_page_produces_no_chunks() -> None:
    page = _make_page([], reading_order=[])
    chunks = chunk_page(page, "doc1", "en")
    assert chunks == []


def test_caption_is_standalone() -> None:
    blocks = [
        CaptionBlock(
            block_id="p0001.b001",
            children=[TextInline(text="Figure 1: Example")],
        ),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 1
    assert chunks[0].text == "Figure 1: Example"


# --- Anchor generation ---


def test_anchor_is_deterministic() -> None:
    a1 = _canonical_anchor("p0001", ["p0001.b001", "p0001.b002"])
    a2 = _canonical_anchor("p0001", ["p0001.b001", "p0001.b002"])
    assert a1 == a2


def test_anchor_differs_for_different_blocks() -> None:
    a1 = _canonical_anchor("p0001", ["p0001.b001"])
    a2 = _canonical_anchor("p0001", ["p0001.b002"])
    assert a1 != a2


def test_anchor_format() -> None:
    anchor = _canonical_anchor("p0042", ["p0042.b001"])
    assert anchor.startswith("chunk.0042.")
    assert len(anchor.split(".")) == 3


# --- Text extraction ---


def test_extract_text_with_icons_as_word_boundaries() -> None:
    """Non-text inlines should produce word boundaries, not be silently dropped."""
    blocks: list[Block] = [
        ParagraphBlock(
            block_id="p0001.b001",
            children=[
                TextInline(text="Roll"),
                IconInline(symbol_id="dice", instance_id="i1"),
                TextInline(text="then move"),
            ],
        ),
    ]
    text = _extract_text(blocks)
    assert text == "Roll then move"


def test_extract_text_multiple_blocks() -> None:
    blocks: list[Block] = [
        ParagraphBlock(
            block_id="p0001.b001",
            children=[TextInline(text="First block.")],
        ),
        ParagraphBlock(
            block_id="p0001.b002",
            children=[TextInline(text="Second block.")],
        ),
    ]
    text = _extract_text(blocks)
    assert text == "First block. Second block."


# --- Normalized text ---


def test_normalize_text() -> None:
    assert _normalize_text("  Hello   WORLD  ") == "hello world"


# --- Concept harvesting ---


def test_glossary_concepts_harvested() -> None:
    blocks = [
        ParagraphBlock(
            block_id="p0001.b001",
            children=[
                TextInline(text="Use "),
                TermMarkInline(concept_id="c_focus", surface_form="Focus"),
                TextInline(text=" action."),
            ],
        ),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks) == 1
    assert len(chunks[0].glossary_concepts) == 1
    assert chunks[0].glossary_concepts[0].concept_id == "c_focus"
    assert chunks[0].glossary_concepts[0].surface_form == "Focus"


def test_duplicate_concepts_deduplicated() -> None:
    blocks = [
        ParagraphBlock(
            block_id="p0001.b001",
            children=[
                TermMarkInline(concept_id="c_focus", surface_form="Focus"),
                TextInline(text=" and "),
                TermMarkInline(concept_id="c_focus", surface_form="Focus"),
                TextInline(text=" again."),
            ],
        ),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks[0].glossary_concepts) == 1


# --- Symbol harvesting ---


def test_symbol_ids_harvested() -> None:
    blocks = [
        ParagraphBlock(
            block_id="p0001.b001",
            children=[
                TextInline(text="Roll "),
                IconInline(symbol_id="dice_d6", instance_id="i1"),
            ],
        ),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert chunks[0].symbol_ids == ["dice_d6"]


# --- Deep link ---


def test_deep_link_format() -> None:
    blocks = [_para("p0001.b001", "Hello.")]
    page = _make_page(blocks)
    chunks = chunk_page(page, "my_doc", "en")
    assert chunks[0].deep_link.startswith("/documents/my_doc/en/p0001#anchor=chunk.")


# --- Section path ---


def test_section_path_from_hint() -> None:
    blocks = [_para("p0001.b001", "Hello.")]
    hint = SectionHint(section_id="s1", path=["Chapter 1", "Rules"])
    page = _make_page(blocks, section_hint=hint)
    chunks = chunk_page(page, "doc1", "en")
    assert chunks[0].section_path == ["Chapter 1", "Rules"]


# --- Facsimile bbox refs ---


def test_bbox_refs_normalized() -> None:
    blocks = [
        ParagraphBlock(
            block_id="p0001.b001",
            bbox=Rect(x0=0.0, y0=0.0, x1=300.0, y1=100.0),
            children=[TextInline(text="Hello.")],
        ),
    ]
    page = _make_page(blocks, dimensions=PageDimensions(width=600.0, height=800.0))
    chunks = chunk_page(page, "doc1", "en")
    assert len(chunks[0].facsimile_bbox_refs) == 1
    ref = chunks[0].facsimile_bbox_refs[0]
    assert abs(ref.x1 - 0.5) < 0.001
    assert abs(ref.y1 - 0.125) < 0.001


def test_no_bbox_refs_without_dimensions() -> None:
    blocks = [
        ParagraphBlock(
            block_id="p0001.b001",
            bbox=Rect(x0=0.0, y0=0.0, x1=300.0, y1=100.0),
            children=[TextInline(text="Hello.")],
        ),
    ]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert chunks[0].facsimile_bbox_refs == []


# --- Rule chunk ID and edition ---


def test_rule_chunk_id_includes_language() -> None:
    blocks = [_para("p0001.b001", "Hello.")]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert chunks[0].rule_chunk_id.endswith(".en")


def test_edition_propagated() -> None:
    blocks = [_para("p0001.b001", "Hello.")]
    page = _make_page(blocks)
    chunks = chunk_page(page, "doc1", "en")
    assert chunks[0].edition == "en"
