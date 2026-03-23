"""Tests for block post-processing: paragraph splitting and deduplication."""

from __future__ import annotations

from atr_pipeline.stages.structure.block_postprocess import (
    deduplicate_blocks,
    split_long_paragraphs,
)
from atr_schemas.common import Rect
from atr_schemas.page_ir_v1 import HeadingBlock, ParagraphBlock, TextInline


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _para(bid: str, text: str, bbox: Rect | None = None) -> ParagraphBlock:
    return ParagraphBlock(block_id=bid, bbox=bbox, children=[TextInline(text=text)])


class TestSplitLongParagraphsPreservesBbox:
    """Regression: split_long_paragraphs must preserve the original bbox."""

    def test_split_preserves_bbox_on_all_parts(self) -> None:
        bbox = _rect(50, 100, 500, 400)
        long_text = "First sentence. " * 50  # > 600 chars
        block = _para("b1", long_text, bbox=bbox)

        result = split_long_paragraphs([block], max_chars=600)
        assert len(result) >= 2, "Should split into at least 2 parts"
        for part in result:
            assert isinstance(part, ParagraphBlock)
            assert part.bbox == bbox, f"Part {part.block_id} lost its bbox"

    def test_no_split_preserves_bbox(self) -> None:
        bbox = _rect(50, 100, 500, 120)
        block = _para("b1", "Short text.", bbox=bbox)

        result = split_long_paragraphs([block], max_chars=600)
        assert len(result) == 1
        assert isinstance(result[0], ParagraphBlock)
        assert result[0].bbox == bbox

    def test_split_preserves_none_bbox(self) -> None:
        long_text = "Another sentence. " * 50
        block = _para("b1", long_text, bbox=None)

        result = split_long_paragraphs([block], max_chars=600)
        assert len(result) >= 2
        for part in result:
            assert isinstance(part, ParagraphBlock)
            assert part.bbox is None

    def test_non_paragraph_blocks_untouched(self) -> None:
        heading = HeadingBlock(
            block_id="h1",
            bbox=_rect(50, 50, 400, 70),
            level=1,
            children=[TextInline(text="Title")],
        )
        result = split_long_paragraphs([heading], max_chars=600)
        assert len(result) == 1
        assert result[0] is heading

    def test_no_sentence_boundary_preserves_bbox(self) -> None:
        """When no sentence boundary is found, the block is kept whole with bbox."""
        bbox = _rect(10, 20, 300, 40)
        block = _para("b1", "x" * 700, bbox=bbox)

        result = split_long_paragraphs([block], max_chars=600)
        assert len(result) == 1
        assert isinstance(result[0], ParagraphBlock)
        assert result[0].bbox == bbox


class TestDeduplicateBlocks:
    def test_removes_consecutive_duplicates(self) -> None:
        blocks = [_para("b1", "Same text"), _para("b2", "Same text")]
        result = deduplicate_blocks(blocks)
        assert len(result) == 1

    def test_keeps_non_consecutive_duplicates(self) -> None:
        blocks = [
            _para("b1", "Text A"),
            _para("b2", "Text B"),
            _para("b3", "Text A"),
        ]
        result = deduplicate_blocks(blocks)
        assert len(result) == 3
