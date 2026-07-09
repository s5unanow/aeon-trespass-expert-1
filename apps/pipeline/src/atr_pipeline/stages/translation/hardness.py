"""Pure deterministic hardness scoring for translation batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_schemas.page_ir_v1 import (
    Block,
    IconInline,
    InlineNode,
    PageIRV1,
    TableBlock,
    TextInline,
    XrefInline,
    iter_table_inlines,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment

_ROUND_DIGITS = 6


@dataclass(frozen=True)
class SignalContribution:
    """One normalized signal and its weighted score contribution."""

    raw_value: float
    normalized_value: float
    weight: float
    contribution: float

    def to_metadata(self) -> dict[str, float]:
        return {
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "weight": self.weight,
            "contribution": self.contribution,
        }


@dataclass(frozen=True)
class HardnessAssessment:
    """Deterministic routing decision for a translation batch."""

    score: float
    threshold: float
    is_hard: bool
    signals: dict[str, SignalContribution]

    def to_metadata(self) -> dict[str, object]:
        return {
            "score": self.score,
            "threshold": self.threshold,
            "is_hard": self.is_hard,
            "signals": {name: signal.to_metadata() for name, signal in self.signals.items()},
        }


def _round(value: float) -> float:
    return round(value, _ROUND_DIGITS)


def _normalize(raw_value: float, reference: float) -> float:
    return _round(min(raw_value / reference, 1.0))


def _signal(raw_value: float, reference: float, weight: float) -> SignalContribution:
    normalized = _normalize(raw_value, reference)
    return SignalContribution(
        raw_value=_round(raw_value),
        normalized_value=normalized,
        weight=_round(weight),
        contribution=_round(normalized * weight),
    )


def _block_inlines(block: Block) -> list[InlineNode]:
    if isinstance(block, TableBlock):
        return iter_table_inlines(block)
    children = getattr(block, "children", [])
    if not isinstance(children, list):
        return []
    return cast(list[InlineNode], children)


def _all_page_inlines(page_ir: PageIRV1) -> list[InlineNode]:
    inlines: list[InlineNode] = []
    for block in page_ir.blocks:
        inlines.extend(_block_inlines(block))
    return inlines


def _segment_text_length(segment: TranslationSegment) -> int:
    return sum(len(node.text) for node in segment.source_inline if isinstance(node, TextInline))


def assess_translation_hardness(
    page_ir: PageIRV1,
    batch: TranslationBatchV1,
    config: TranslationHardnessConfig,
) -> HardnessAssessment:
    """Score a page/batch from pre-translation PageIR and batch signals.

    A score equal to the threshold is considered hard. The function performs no
    I/O and depends only on its explicit inputs, so repeated calls over the same
    PageIR, batch, and config produce identical results.
    """
    inlines = _all_page_inlines(page_ir)
    inline_count = len(inlines)
    density_denominator = float(max(inline_count, 1))
    icon_density = sum(1 for node in inlines if isinstance(node, IconInline)) / density_denominator
    xref_density = sum(1 for node in inlines if isinstance(node, XrefInline)) / density_denominator
    has_table = any(isinstance(block, TableBlock) for block in page_ir.blocks)
    max_segment_length = max(
        (_segment_text_length(segment) for segment in batch.segments),
        default=0,
    )

    weights = config.weights
    signals = {
        "inline_icon_density": _signal(
            icon_density,
            config.icon_density_reference,
            weights.inline_icon_density,
        ),
        "cross_reference_density": _signal(
            xref_density,
            config.xref_density_reference,
            weights.cross_reference_density,
        ),
        "table_presence": SignalContribution(
            raw_value=1.0 if has_table else 0.0,
            normalized_value=1.0 if has_table else 0.0,
            weight=_round(weights.table_presence),
            contribution=_round((1.0 if has_table else 0.0) * weights.table_presence),
        ),
        "segment_count": _signal(
            float(len(batch.segments)),
            float(config.segment_count_reference),
            weights.segment_count,
        ),
        "segment_length": _signal(
            float(max_segment_length),
            float(config.segment_length_reference),
            weights.segment_length,
        ),
    }
    score = _round(sum(signal.contribution for signal in signals.values()))
    threshold = _round(config.threshold)
    return HardnessAssessment(
        score=score,
        threshold=threshold,
        is_hard=score >= threshold,
        signals=signals,
    )
