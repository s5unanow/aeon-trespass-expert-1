"""Deterministic page/batch hardness classifier for translation routing.

S5U-1542 — hard pages (icon-dense, xref-dense, table-heavy) should escalate to
``TranslationConfig.model_hard``. This module scores a ``TranslationBatchV1``
from signals available *before* translation and returns a pure, deterministic
verdict plus a per-signal breakdown for provenance.

The score is a linear model over four signals:

* ``icon_density``   — inline icons per segment
* ``xref_density``   — real cross-references per segment (narrative-group
  boundary markers are synthetic and excluded)
* ``table_ratio``    — fraction of segments that are table cells / tables
* ``segment_load``   — segment count (a proxy for page size/length)

``score = Σ weight_i * signal_i`` and ``is_hard = score >= threshold``. Every
input is the batch content and the config weights, so the same batch always
produces the same score — a requirement for reproducible provenance.
"""

from __future__ import annotations

from dataclasses import dataclass

from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.stages.translation.grouping import is_group_marker
from atr_schemas.page_ir_v1 import IconInline, TextInline, XrefInline
from atr_schemas.translation_batch_v1 import TranslationBatchV1

# Segment ``block_type`` values that represent tabular content. Structured
# tables emit one ``table_cell`` segment per cell; legacy flat tables emit a
# single ``table`` segment (see planner ``_emit_table_cell_segments`` /
# ``_emit_block_segment``).
_TABLE_BLOCK_TYPES = frozenset({"table", "table_cell"})


@dataclass(frozen=True)
class HardnessSignals:
    """Raw, integer signal counts collected from a batch."""

    segment_count: int
    icon_count: int
    xref_count: int
    table_segment_count: int
    char_count: int


@dataclass(frozen=True)
class HardnessScore:
    """Result of scoring a batch: verdict plus a full provenance breakdown."""

    score: float
    threshold: float
    is_hard: bool
    features: dict[str, float]
    contributions: dict[str, float]
    signals: HardnessSignals

    def to_metadata(self) -> dict[str, object]:
        """Return a deterministic, JSON-serializable provenance dict.

        The stage merges this into the per-page ``translation_meta.v1`` record
        (adding the routed ``chosen_model``). Because every value derives from
        the batch content and config weights, two runs on identical inputs
        produce byte-identical metadata (AC 4).
        """
        return {
            "score": self.score,
            "threshold": self.threshold,
            "is_hard": self.is_hard,
            "features": dict(self.features),
            "contributions": dict(self.contributions),
            "signals": {
                "segment_count": self.signals.segment_count,
                "icon_count": self.signals.icon_count,
                "xref_count": self.signals.xref_count,
                "table_segment_count": self.signals.table_segment_count,
                "char_count": self.signals.char_count,
            },
        }


def _collect_signals(batch: TranslationBatchV1) -> HardnessSignals:
    """Count icons, real xrefs, table segments, and characters in *batch*."""
    icon_count = 0
    xref_count = 0
    table_segment_count = 0
    char_count = 0
    for segment in batch.segments:
        if segment.block_type in _TABLE_BLOCK_TYPES:
            table_segment_count += 1
        for node in segment.source_inline:
            if isinstance(node, IconInline):
                icon_count += 1
            elif isinstance(node, XrefInline):
                # Narrative-group boundary markers are synthetic xrefs the
                # planner inserts; they are not real cross-references.
                if not is_group_marker(node):
                    xref_count += 1
            elif isinstance(node, TextInline):
                char_count += len(node.text)
    return HardnessSignals(
        segment_count=len(batch.segments),
        icon_count=icon_count,
        xref_count=xref_count,
        table_segment_count=table_segment_count,
        char_count=char_count,
    )


def classify_hardness(
    batch: TranslationBatchV1,
    config: TranslationHardnessConfig,
) -> HardnessScore:
    """Score *batch* against *config* and return the hard/easy verdict.

    Pure and deterministic: no I/O, no clock, no randomness. Callers gate on
    ``config.enabled`` before invoking — this function always computes a score.
    """
    signals = _collect_signals(batch)
    n = signals.segment_count
    if n > 0:
        icon_density = signals.icon_count / n
        xref_density = signals.xref_count / n
        table_ratio = signals.table_segment_count / n
    else:
        icon_density = xref_density = table_ratio = 0.0
    segment_load = float(n)

    features = {
        "icon_density": icon_density,
        "xref_density": xref_density,
        "table_ratio": table_ratio,
        "segment_load": segment_load,
    }
    contributions = {
        "icon_density": config.weight_icon_density * icon_density,
        "xref_density": config.weight_xref_density * xref_density,
        "table_ratio": config.weight_table_ratio * table_ratio,
        "segment_load": config.weight_segment_load * segment_load,
    }
    score = sum(contributions.values())
    return HardnessScore(
        score=score,
        threshold=config.threshold,
        is_hard=score >= config.threshold,
        features=features,
        contributions=contributions,
        signals=signals,
    )
