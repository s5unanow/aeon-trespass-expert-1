"""Hardness classifier for translation-stage model routing (S5U-1541).

Pure deterministic function of batch content. Scores pages/batches using
inline icon density, cross-reference density (excluding internal group
markers), table block presence, and segment/character volume.

All weights, threshold, and enable flag come from TOML-validated
HardnessConfig. Default-disabled so existing runs and metadata are
byte-identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atr_pipeline.config.models import HardnessConfig
from atr_pipeline.stages.translation.grouping import is_group_marker
from atr_schemas.page_ir_v1 import IconInline, TextInline, XrefInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1


@dataclass(frozen=True)
class HardnessSignals:
    """Raw deterministic signal counts extracted from a translation batch."""

    icon_count: int
    xref_count: int
    table_presence: int  # 0 or 1 (presence, not count of cells)
    segment_count: int
    char_count: int


@dataclass(frozen=True)
class HardnessResult:
    """Classification outcome for one batch/page.

    Reproducible on identical batch + config: same inputs yield identical
    score, breakdown, and chosen_model.
    """

    score: float
    threshold: float
    enabled: bool
    chosen_model: str
    signals: HardnessSignals
    signal_breakdown: dict[str, float]

    def to_meta_dict(self) -> dict[str, Any]:
        """Serializable subset for embedding in translation_meta.v1."""
        return {
            "score": self.score,
            "threshold": self.threshold,
            "signals": {
                "icon_count": self.signals.icon_count,
                "xref_count": self.signals.xref_count,
                "table_presence": self.signals.table_presence,
                "segment_count": self.signals.segment_count,
                "char_count": self.signals.char_count,
            },
            "signal_breakdown": dict(self.signal_breakdown),
        }


def _compute_signals(batch: TranslationBatchV1) -> HardnessSignals:
    """Pure count extraction. No mutation, no randomness."""
    icon_count = 0
    xref_count = 0
    table_presence = 0
    segment_count = len(batch.segments)
    char_count = 0

    for seg in batch.segments:
        if seg.block_type == "table_cell":
            table_presence = 1
        for node in seg.source_inline:
            if isinstance(node, IconInline):
                icon_count += 1
            elif isinstance(node, XrefInline) and not is_group_marker(node):
                xref_count += 1
            if isinstance(node, TextInline):
                char_count += len(getattr(node, "text", "") or "")

    return HardnessSignals(
        icon_count=icon_count,
        xref_count=xref_count,
        table_presence=table_presence,
        segment_count=segment_count,
        char_count=char_count,
    )


def compute_hardness(
    batch: TranslationBatchV1,
    hardness: HardnessConfig,
    model_default: str,
    model_hard: str,
) -> HardnessResult:
    """Pure deterministic hardness classifier + router decision.

    Returns score in [0, ~1], chosen model, full signal breakdown.
    When ``hardness.enabled`` is false, always returns score=0.0 and
    model_default (no side effects on caller).
    """
    signals = _compute_signals(batch)

    if not hardness.enabled:
        return HardnessResult(
            score=0.0,
            threshold=hardness.threshold,
            enabled=False,
            chosen_model=model_default,
            signals=signals,
            signal_breakdown={},
        )

    # Densities capped at 1.0 for stability
    icon_d = min(1.0, signals.icon_count / 10.0)
    xref_d = min(1.0, signals.xref_count / 4.0)
    table_d = float(signals.table_presence)
    len_d = min(1.0, (signals.segment_count / 15.0) + (signals.char_count / 2500.0))

    w_sum = (
        hardness.icon_weight + hardness.xref_weight + hardness.table_weight + hardness.length_weight
    )
    if w_sum <= 0.0:
        score = 0.0
    else:
        score = (
            hardness.icon_weight * icon_d
            + hardness.xref_weight * xref_d
            + hardness.table_weight * table_d
            + hardness.length_weight * len_d
        ) / w_sum

    chosen = model_hard if score >= hardness.threshold else model_default

    breakdown: dict[str, float] = {
        "icon_density": round(icon_d, 6),
        "xref_density": round(xref_d, 6),
        "table_presence": table_d,
        "length_factor": round(len_d, 6),
        "weighted_score": round(score, 6),
    }

    return HardnessResult(
        score=round(score, 6),
        threshold=hardness.threshold,
        enabled=True,
        chosen_model=chosen,
        signals=signals,
        signal_breakdown=breakdown,
    )
