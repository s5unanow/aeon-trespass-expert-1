"""Pure deterministic scoring for translation model routing."""

from __future__ import annotations

from dataclasses import dataclass

from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.stages.translation.grouping import is_group_marker
from atr_schemas.page_ir_v1 import IconInline, PageIRV1, TableBlock, TextInline, XrefInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1


@dataclass(frozen=True)
class HardnessAssessment:
    """Reproducible score plus the raw and weighted signal breakdown."""

    score: float
    signals: dict[str, float]
    contributions: dict[str, float]
    threshold: float
    is_hard: bool

    def metadata(
        self,
        *,
        selected_primary_model: str,
        chosen_model: str,
    ) -> dict[str, object]:
        """Return the JSON-ready provenance stored beside a translated batch."""
        return {
            "score": self.score,
            "signals": self.signals,
            "contributions": self.contributions,
            "threshold": self.threshold,
            "is_hard": self.is_hard,
            "selected_primary_model": selected_primary_model,
            "chosen_model": chosen_model,
        }


def classify_hardness(
    page: PageIRV1,
    batch: TranslationBatchV1,
    config: TranslationHardnessConfig,
) -> HardnessAssessment:
    """Score one planned page batch using only stable pre-translation data."""
    source_inline = [
        node
        for segment in batch.segments
        for node in segment.source_inline
        if not (isinstance(node, XrefInline) and is_group_marker(node))
    ]
    inline_count = len(source_inline)
    icon_count = sum(isinstance(node, IconInline) for node in source_inline)
    xref_count = sum(isinstance(node, XrefInline) for node in source_inline)
    text_length = sum(len(node.text) for node in source_inline if isinstance(node, TextInline))
    segment_count = len(batch.segments)

    signals = {
        "inline_icon_density": icon_count / inline_count if inline_count else 0.0,
        "cross_reference_density": xref_count / inline_count if inline_count else 0.0,
        "table_presence": float(any(isinstance(block, TableBlock) for block in page.blocks)),
        "segment_count": float(segment_count),
        "average_segment_length": text_length / segment_count if segment_count else 0.0,
    }
    contributions = {
        "inline_icon_density": (signals["inline_icon_density"] * config.inline_icon_density_weight),
        "cross_reference_density": (
            signals["cross_reference_density"] * config.cross_reference_density_weight
        ),
        "table_presence": signals["table_presence"] * config.table_presence_weight,
        "segment_count": signals["segment_count"] * config.segment_count_weight,
        "average_segment_length": (
            signals["average_segment_length"] * config.segment_length_weight
        ),
    }
    score = sum(contributions.values())
    return HardnessAssessment(
        score=score,
        signals=signals,
        contributions=contributions,
        threshold=config.threshold,
        is_hard=score >= config.threshold,
    )
