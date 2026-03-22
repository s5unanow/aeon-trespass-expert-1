"""Tests for deterministic page confidence scorer."""

from __future__ import annotations

import pytest

from atr_pipeline.eval.confidence_scorer import (
    ScoringInputs,
    collect_signals,
    score_page,
    score_page_from_artifacts,
)
from atr_schemas.common import Rect
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)

# ── Helper factories ──────────────────────────────────────────────────


def _make_page_ir(
    *,
    block_count: int = 3,
    ordered_count: int | None = None,
    icon_confidences: list[float] | None = None,
) -> PageIRV1:
    """Build a minimal PageIRV1 with configurable blocks and reading order."""
    blocks: list[HeadingBlock | ParagraphBlock] = []
    for i in range(block_count):
        bid = f"p0001.b{i:03d}"
        children = [TextInline(text=f"text {i}")]
        if icon_confidences and i < len(icon_confidences):
            children.append(
                IconInline(
                    symbol_id=f"sym_{i}",
                    bbox=Rect(x0=0, y0=0, x1=10, y1=10),
                    confidence=icon_confidences[i],
                )
            )
        blocks.append(ParagraphBlock(block_id=bid, children=children))

    if ordered_count is None:
        ordered_count = block_count
    reading_order = [f"p0001.b{i:03d}" for i in range(ordered_count)]

    return PageIRV1(
        document_id="test_doc",
        page_id="p0001",
        page_number=1,
        language="en",
        blocks=blocks,
        reading_order=reading_order,
    )


def _make_difficulty(
    *,
    native_text_coverage: float = 0.85,
    hard_page: bool = False,
) -> DifficultyScoreV1:
    return DifficultyScoreV1(
        page_id="p0001",
        native_text_coverage=native_text_coverage,
        hard_page=hard_page,
    )


# ── Signal collection ─────────────────────────────────────────────────


class TestCollectSignals:
    """Tests for collect_signals()."""

    def test_no_artifacts_returns_defaults(self) -> None:
        """All defaults = perfect scores."""
        inputs = collect_signals()
        assert inputs.native_text_coverage == 1.0
        assert inputs.reading_order_completeness == 1.0
        assert inputs.symbol_confidence_mean == 1.0

    def test_difficulty_provides_text_coverage(self) -> None:
        diff = _make_difficulty(native_text_coverage=0.42)
        inputs = collect_signals(difficulty=diff)
        assert inputs.native_text_coverage == 0.42

    def test_layout_fallback_for_text_coverage(self) -> None:
        """When no difficulty, layout.difficulty is used."""
        layout = LayoutPageV1(
            document_id="test",
            page_id="p0001",
            difficulty=DifficultyScoreV1(page_id="p0001", native_text_coverage=0.55),
        )
        inputs = collect_signals(layout=layout)
        assert inputs.native_text_coverage == 0.55

    def test_difficulty_takes_precedence_over_layout(self) -> None:
        diff = _make_difficulty(native_text_coverage=0.80)
        layout = LayoutPageV1(
            document_id="test",
            page_id="p0001",
            difficulty=DifficultyScoreV1(page_id="p0001", native_text_coverage=0.55),
        )
        inputs = collect_signals(difficulty=diff, layout=layout)
        assert inputs.native_text_coverage == 0.80

    def test_reading_order_complete(self) -> None:
        ir = _make_page_ir(block_count=5, ordered_count=5)
        inputs = collect_signals(page_ir=ir)
        assert inputs.reading_order_completeness == 1.0

    def test_reading_order_partial(self) -> None:
        ir = _make_page_ir(block_count=4, ordered_count=2)
        inputs = collect_signals(page_ir=ir)
        assert inputs.reading_order_completeness == 0.5

    def test_reading_order_empty_page(self) -> None:
        ir = _make_page_ir(block_count=0)
        inputs = collect_signals(page_ir=ir)
        assert inputs.reading_order_completeness == 1.0

    def test_symbol_confidence_mean(self) -> None:
        ir = _make_page_ir(icon_confidences=[0.9, 0.5])
        inputs = collect_signals(page_ir=ir)
        assert inputs.symbol_confidence_mean == pytest.approx(0.7)

    def test_no_icons_perfect_score(self) -> None:
        ir = _make_page_ir(block_count=3)
        inputs = collect_signals(page_ir=ir)
        assert inputs.symbol_confidence_mean == 1.0


# ── Scoring ───────────────────────────────────────────────────────────


class TestScorePage:
    """Tests for score_page()."""

    def test_perfect_inputs(self) -> None:
        inputs = ScoringInputs(
            native_text_coverage=1.0,
            reading_order_completeness=1.0,
            symbol_confidence_mean=1.0,
        )
        metrics = score_page(inputs)
        assert metrics.page_confidence == 1.0
        assert metrics.native_text_coverage == 1.0
        assert metrics.reading_order_score == 1.0
        assert metrics.symbol_score == 1.0

    def test_zero_text_coverage(self) -> None:
        """Very low text coverage should lower page confidence."""
        inputs = ScoringInputs(
            native_text_coverage=0.05,
            reading_order_completeness=1.0,
            symbol_confidence_mean=1.0,
        )
        metrics = score_page(inputs)
        assert metrics.page_confidence < 1.0
        # text_coverage normalized to 0 when <= 0.10
        assert metrics.page_confidence == pytest.approx(0.70, abs=0.01)

    def test_partial_reading_order(self) -> None:
        inputs = ScoringInputs(
            native_text_coverage=0.85,
            reading_order_completeness=0.5,
            symbol_confidence_mean=1.0,
        )
        metrics = score_page(inputs)
        assert metrics.reading_order_score == 0.5
        assert metrics.page_confidence < 1.0

    def test_low_symbol_confidence(self) -> None:
        inputs = ScoringInputs(
            native_text_coverage=0.85,
            reading_order_completeness=1.0,
            symbol_confidence_mean=0.3,
        )
        metrics = score_page(inputs)
        assert metrics.symbol_score == 0.3
        assert metrics.page_confidence < 1.0

    def test_all_signals_degraded(self) -> None:
        """All signals poor -> low confidence, still >= 0."""
        inputs = ScoringInputs(
            native_text_coverage=0.0,
            reading_order_completeness=0.0,
            symbol_confidence_mean=0.0,
        )
        metrics = score_page(inputs)
        assert metrics.page_confidence == 0.0

    def test_page_confidence_clamped(self) -> None:
        """Result always in [0, 1]."""
        inputs = ScoringInputs(
            native_text_coverage=0.5,
            reading_order_completeness=0.5,
            symbol_confidence_mean=0.5,
        )
        metrics = score_page(inputs)
        assert 0.0 <= metrics.page_confidence <= 1.0

    def test_text_coverage_normalization_mid_range(self) -> None:
        """Text coverage between 0.10 and 0.70 should interpolate."""
        inputs = ScoringInputs(
            native_text_coverage=0.40,
            reading_order_completeness=1.0,
            symbol_confidence_mean=1.0,
        )
        metrics = score_page(inputs)
        assert 0.0 < metrics.page_confidence < 1.0


# ── One-shot convenience ──────────────────────────────────────────────


class TestScorePageFromArtifacts:
    """Tests for score_page_from_artifacts()."""

    def test_no_inputs(self) -> None:
        metrics = score_page_from_artifacts()
        assert metrics.page_confidence == 1.0

    def test_with_all_artifacts(self) -> None:
        diff = _make_difficulty(native_text_coverage=0.9)
        ir = _make_page_ir(block_count=4, ordered_count=4, icon_confidences=[0.8])
        metrics = score_page_from_artifacts(difficulty=diff, page_ir=ir)
        assert 0.0 <= metrics.page_confidence <= 1.0
        assert metrics.native_text_coverage == 0.9

    def test_hard_page_lower_confidence(self) -> None:
        """A hard page (low text coverage) should score lower."""
        easy = score_page_from_artifacts(
            difficulty=_make_difficulty(native_text_coverage=0.9),
        )
        hard = score_page_from_artifacts(
            difficulty=_make_difficulty(native_text_coverage=0.15),
        )
        assert hard.page_confidence < easy.page_confidence
