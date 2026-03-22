"""Deterministic page confidence scorer.

Computes ``ConfidenceMetrics`` from extraction signals available at
different pipeline stages.  The scorer is intentionally deterministic —
no ML models — so that confidence is reproducible from the same inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

from atr_schemas.common import ConfidenceMetrics
from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutPageV1
from atr_schemas.page_ir_v1 import IconInline, PageIRV1

# ── Weights for the aggregate page_confidence score ───────────────────

_W_TEXT_COVERAGE = 0.30
_W_READING_ORDER = 0.35
_W_SYMBOL = 0.35

# ── Thresholds for individual signal scoring ──────────────────────────

_GOOD_TEXT_COVERAGE = 0.70
_MIN_TEXT_COVERAGE = 0.10


@dataclass(frozen=True, slots=True)
class ScoringInputs:
    """Collected signals for confidence scoring."""

    native_text_coverage: float
    reading_order_completeness: float
    symbol_confidence_mean: float


def collect_signals(
    *,
    difficulty: DifficultyScoreV1 | None = None,
    layout: LayoutPageV1 | None = None,
    page_ir: PageIRV1 | None = None,
) -> ScoringInputs:
    """Gather deterministic signals from available pipeline artifacts.

    Each input is optional — missing artifacts contribute default scores
    (1.0 = no evidence of problems).
    """
    native_text_coverage = _extract_text_coverage(difficulty, layout)
    reading_order = _extract_reading_order_completeness(page_ir)
    symbol_mean = _extract_symbol_confidence(page_ir)

    return ScoringInputs(
        native_text_coverage=native_text_coverage,
        reading_order_completeness=reading_order,
        symbol_confidence_mean=symbol_mean,
    )


def score_page(inputs: ScoringInputs) -> ConfidenceMetrics:
    """Compute ``ConfidenceMetrics`` from pre-collected signals.

    The aggregate ``page_confidence`` is a weighted combination of the
    three per-aspect scores, clamped to [0, 1].
    """
    text_score = _normalize_text_coverage(inputs.native_text_coverage)
    reading_score = inputs.reading_order_completeness
    symbol_score = inputs.symbol_confidence_mean

    aggregate = (
        _W_TEXT_COVERAGE * text_score + _W_READING_ORDER * reading_score + _W_SYMBOL * symbol_score
    )
    page_confidence = round(max(0.0, min(1.0, aggregate)), 4)

    return ConfidenceMetrics(
        native_text_coverage=round(inputs.native_text_coverage, 4),
        reading_order_score=round(reading_score, 4),
        symbol_score=round(symbol_score, 4),
        page_confidence=page_confidence,
    )


def score_page_from_artifacts(
    *,
    difficulty: DifficultyScoreV1 | None = None,
    layout: LayoutPageV1 | None = None,
    page_ir: PageIRV1 | None = None,
) -> ConfidenceMetrics:
    """One-shot convenience: collect signals and score in one call."""
    inputs = collect_signals(difficulty=difficulty, layout=layout, page_ir=page_ir)
    return score_page(inputs)


# ── Private signal extractors ─────────────────────────────────────────


def _extract_text_coverage(
    difficulty: DifficultyScoreV1 | None,
    layout: LayoutPageV1 | None,
) -> float:
    """Get native text coverage from difficulty score or layout."""
    if difficulty is not None:
        return difficulty.native_text_coverage
    if layout is not None and layout.difficulty is not None:
        return layout.difficulty.native_text_coverage
    return 1.0


def _extract_reading_order_completeness(page_ir: PageIRV1 | None) -> float:
    """Fraction of blocks that appear in the explicit reading order.

    A complete reading order means all block IDs are present.
    Missing order for a page with no blocks is treated as perfect.
    Deduplicates reading order entries and validates against actual block IDs.
    """
    if page_ir is None:
        return 1.0
    block_ids = {b.block_id for b in page_ir.blocks}
    if not block_ids:
        return 1.0
    valid_ordered = set(page_ir.reading_order) & block_ids
    return len(valid_ordered) / len(block_ids)


def _extract_symbol_confidence(page_ir: PageIRV1 | None) -> float:
    """Mean confidence of inline icon nodes.

    Pages with no icons get a perfect score (no evidence of problems).
    """
    if page_ir is None:
        return 1.0

    confidences: list[float] = []
    for block in page_ir.blocks:
        children = getattr(block, "children", None)
        if children is None:
            continue
        for child in children:
            if isinstance(child, IconInline):
                confidences.append(child.confidence)

    if not confidences:
        return 1.0
    return sum(confidences) / len(confidences)


def _normalize_text_coverage(raw: float) -> float:
    """Map raw native_text_coverage to a [0, 1] quality score.

    Coverage above ``_GOOD_TEXT_COVERAGE`` is full confidence.
    Coverage below ``_MIN_TEXT_COVERAGE`` is zero confidence.
    Between those, interpolate linearly.
    """
    if raw >= _GOOD_TEXT_COVERAGE:
        return 1.0
    if raw <= _MIN_TEXT_COVERAGE:
        return 0.0
    return (raw - _MIN_TEXT_COVERAGE) / (_GOOD_TEXT_COVERAGE - _MIN_TEXT_COVERAGE)
