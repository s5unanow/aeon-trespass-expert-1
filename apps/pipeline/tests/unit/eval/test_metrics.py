"""Tests for evaluation metrics."""

from __future__ import annotations

from atr_pipeline.eval.metrics import (
    BlockCountDelta,
    BlockTypeCoverage,
    EvalMetric,
    ReadingOrderAccuracy,
    SymbolCount,
    get_default_metrics,
)
from atr_pipeline.eval.models import GoldenPageSpec
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)


def _make_ir(
    blocks: list[object] | None = None,
    reading_order: list[str] | None = None,
) -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        blocks=blocks or [],
        reading_order=reading_order or [],
    )


def _make_spec(
    block_count: int = 2,
    block_types: list[str] | None = None,
    symbol_count: int = 0,
    reading_order: list[str] | None = None,
) -> GoldenPageSpec:
    return GoldenPageSpec(
        page_id="p0001",
        block_count=block_count,
        block_types=block_types or [],
        symbol_count=symbol_count,
        reading_order=reading_order or [],
    )


class TestBlockCountDelta:
    def test_exact_match(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                ParagraphBlock(block_id="p0001.b002"),
            ]
        )
        result = BlockCountDelta().evaluate(ir, _make_spec(block_count=2))
        assert result.passed
        assert result.value == 2.0

    def test_mismatch(self) -> None:
        ir = _make_ir(blocks=[HeadingBlock(block_id="p0001.b001")])
        result = BlockCountDelta().evaluate(ir, _make_spec(block_count=3))
        assert not result.passed
        assert result.value == 1.0
        assert result.expected == 3.0

    def test_extra_blocks(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                ParagraphBlock(block_id="p0001.b002"),
                ParagraphBlock(block_id="p0001.b003"),
            ]
        )
        result = BlockCountDelta().evaluate(ir, _make_spec(block_count=2))
        assert not result.passed
        assert "delta=1" in result.detail


class TestSymbolCount:
    def test_no_symbols(self) -> None:
        ir = _make_ir(
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[TextInline(text="hello")],
                ),
            ]
        )
        result = SymbolCount().evaluate(ir, _make_spec(symbol_count=0))
        assert result.passed

    def test_symbol_present(self) -> None:
        ir = _make_ir(
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[IconInline(symbol_id="sym_001")],
                ),
            ]
        )
        result = SymbolCount().evaluate(ir, _make_spec(symbol_count=1))
        assert result.passed
        assert result.value == 1.0

    def test_symbol_mismatch(self) -> None:
        ir = _make_ir(
            blocks=[
                ParagraphBlock(
                    block_id="p0001.b001",
                    children=[TextInline(text="no symbols")],
                ),
            ]
        )
        result = SymbolCount().evaluate(ir, _make_spec(symbol_count=2))
        assert not result.passed
        assert result.value == 0.0


class TestBlockTypeCoverage:
    def test_all_types_present(self) -> None:
        ir = _make_ir(
            blocks=[
                HeadingBlock(block_id="p0001.b001"),
                ParagraphBlock(block_id="p0001.b002"),
            ]
        )
        result = BlockTypeCoverage().evaluate(ir, _make_spec(block_types=["heading", "paragraph"]))
        assert result.passed
        assert result.value == 1.0

    def test_missing_type(self) -> None:
        ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001")])
        result = BlockTypeCoverage().evaluate(ir, _make_spec(block_types=["heading", "paragraph"]))
        assert not result.passed
        assert result.value == 0.5
        assert "heading" in result.detail

    def test_empty_expected(self) -> None:
        ir = _make_ir(blocks=[ParagraphBlock(block_id="p0001.b001")])
        result = BlockTypeCoverage().evaluate(ir, _make_spec(block_types=[]))
        assert result.passed


class TestReadingOrderAccuracy:
    def test_exact_match(self) -> None:
        order = ["p0001.b001", "p0001.b002"]
        ir = _make_ir(reading_order=order)
        result = ReadingOrderAccuracy().evaluate(ir, _make_spec(reading_order=order))
        assert result.passed
        assert result.value == 1.0

    def test_wrong_order(self) -> None:
        ir = _make_ir(reading_order=["p0001.b002", "p0001.b001"])
        spec = _make_spec(reading_order=["p0001.b001", "p0001.b002"])
        result = ReadingOrderAccuracy().evaluate(ir, spec)
        assert not result.passed
        assert result.value == 0.0

    def test_partial_match(self) -> None:
        ir = _make_ir(reading_order=["p0001.b001", "p0001.b003"])
        spec = _make_spec(reading_order=["p0001.b001", "p0001.b002"])
        result = ReadingOrderAccuracy().evaluate(ir, spec)
        assert not result.passed
        assert result.value == 0.5

    def test_empty_expected(self) -> None:
        ir = _make_ir(reading_order=["p0001.b001"])
        result = ReadingOrderAccuracy().evaluate(ir, _make_spec(reading_order=[]))
        assert result.passed

    def test_empty_actual(self) -> None:
        ir = _make_ir(reading_order=[])
        result = ReadingOrderAccuracy().evaluate(ir, _make_spec(reading_order=["p0001.b001"]))
        assert not result.passed
        assert result.value == 0.0


def test_all_metrics_satisfy_protocol() -> None:
    for m in get_default_metrics():
        assert isinstance(m, EvalMetric)
