"""Tests for block-level diff comparator."""

from __future__ import annotations

from atr_pipeline.eval.comparator import compare_blocks, compare_reading_order
from atr_schemas.page_ir_v1 import HeadingBlock, PageIRV1, ParagraphBlock, TableBlock


def _make_ir(blocks: list[object] | None = None) -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        blocks=blocks or [],
    )


class TestCompareBlocks:
    def test_all_match(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                ParagraphBlock(block_id="p0001.b002"),
            ]
        )
        expected = {"p0001.b001": "heading", "p0001.b002": "paragraph"}
        result = compare_blocks(ir, expected)
        assert result.all_match
        assert result.match_count == 2
        assert result.missing_count == 0
        assert result.extra_count == 0

    def test_missing_block(self) -> None:
        ir = _make_ir(blocks=[HeadingBlock(block_id="p0001.b001")])
        expected = {"p0001.b001": "heading", "p0001.b002": "paragraph"}
        result = compare_blocks(ir, expected)
        assert not result.all_match
        assert result.missing_count == 1

    def test_extra_block(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                ParagraphBlock(block_id="p0001.b002"),
                ParagraphBlock(block_id="p0001.b003"),
            ]
        )
        expected = {"p0001.b001": "heading", "p0001.b002": "paragraph"}
        result = compare_blocks(ir, expected)
        assert not result.all_match
        assert result.extra_count == 1

    def test_type_mismatch(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                TableBlock(block_id="p0001.b002"),
            ]
        )
        expected = {"p0001.b001": "heading", "p0001.b002": "paragraph"}
        result = compare_blocks(ir, expected)
        assert not result.all_match
        assert result.mismatch_count == 1

    def test_empty_expected(self) -> None:
        ir = _make_ir(blocks=[HeadingBlock(block_id="p0001.b001")])
        result = compare_blocks(ir, {})
        assert result.extra_count == 1

    def test_empty_actual(self) -> None:
        ir = _make_ir(blocks=[])
        expected = {"p0001.b001": "heading"}
        result = compare_blocks(ir, expected)
        assert result.missing_count == 1


class TestCompareReadingOrder:
    def test_exact_match(self) -> None:
        order = ["p0001.b001", "p0001.b002"]
        diffs = compare_reading_order(order, order)
        assert all(d.status == "match" for d in diffs)

    def test_swapped_order(self) -> None:
        actual = ["p0001.b002", "p0001.b001"]
        expected = ["p0001.b001", "p0001.b002"]
        diffs = compare_reading_order(actual, expected)
        assert all(d.status == "type_mismatch" for d in diffs)

    def test_missing_in_actual(self) -> None:
        actual = ["p0001.b001"]
        expected = ["p0001.b001", "p0001.b002"]
        diffs = compare_reading_order(actual, expected)
        assert diffs[0].status == "match"
        assert diffs[1].status == "missing"

    def test_extra_in_actual(self) -> None:
        actual = ["p0001.b001", "p0001.b002"]
        expected = ["p0001.b001"]
        diffs = compare_reading_order(actual, expected)
        assert diffs[0].status == "match"
        assert diffs[1].status == "extra"
