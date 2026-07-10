"""S5U-1542 — deterministic hardness classifier (pure logic).

The classifier scores a ``TranslationBatchV1`` from signals available before
translation: inline icon density, cross-reference density, table-block
presence, and segment count. The score, per-signal contributions, and hard/
easy verdict must be a pure, deterministic function of the batch + config.
"""

from __future__ import annotations

from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.stages.translation.grouping import GROUP_MARKER_PREFIX
from atr_pipeline.stages.translation.hardness import classify_hardness
from atr_schemas.page_ir_v1 import IconInline, InlineNode, TextInline, XrefInline
from atr_schemas.translation_batch_v1 import (
    TranslationBatchV1,
    TranslationSegment,
)


def _seg(
    segment_id: str,
    block_type: str,
    inline: list[InlineNode],
) -> TranslationSegment:
    return TranslationSegment(
        segment_id=segment_id,
        block_type=block_type,
        source_inline=inline,
    )


def _batch(segments: list[TranslationSegment]) -> TranslationBatchV1:
    return TranslationBatchV1(batch_id="tr.p0001.01", segments=segments)


def _text(s: str) -> TextInline:
    return TextInline(text=s)


def _icon(sym: str = "sym.progress") -> IconInline:
    return IconInline(symbol_id=sym)


def _xref(target: str = "s.42") -> XrefInline:
    return XrefInline(target_section_id=target, label="see")


def _default_cfg(**overrides: object) -> TranslationHardnessConfig:
    params: dict[str, object] = {"enabled": True, "threshold": 2.0}
    params.update(overrides)
    return TranslationHardnessConfig.model_validate(params)


# ── Easy vs hard ──────────────────────────────────────────────────────


def test_easy_page_scores_below_threshold() -> None:
    """A single plain paragraph is well below any sane threshold."""
    batch = _batch([_seg("b1", "paragraph", [_text("Just prose.")])])
    score = classify_hardness(batch, _default_cfg())
    assert score.is_hard is False
    assert score.signals.icon_count == 0
    assert score.signals.xref_count == 0
    assert score.signals.table_segment_count == 0
    assert score.score < 2.0


def test_hard_page_scores_above_threshold() -> None:
    """An icon/xref-dense, table-heavy page routes hard."""
    cells = [
        _seg(f"c{i}", "table_cell", [_icon(), _xref(f"s.{i}"), _text("cell")]) for i in range(6)
    ]
    score = classify_hardness(_batch(cells), _default_cfg())
    assert score.is_hard is True
    assert score.signals.icon_count == 6
    assert score.signals.xref_count == 6
    assert score.signals.table_segment_count == 6
    # icon_density=1.0, xref_density=1.0, table_ratio=1.0, segment_load=6
    # score = 1*1 + 1*1 + 1*1 + 0.05*6 = 3.3 (default weights)
    assert score.score == 3.3


# ── Signal breakdown correctness ──────────────────────────────────────


def test_feature_and_contribution_breakdown() -> None:
    """Per-signal features and weighted contributions are exposed exactly."""
    cfg = _default_cfg(
        weight_icon_density=2.0,
        weight_xref_density=1.0,
        weight_table_ratio=0.5,
        weight_segment_load=0.0,
    )
    # 2 segments; segment 0 has 2 icons + 1 xref; segment 1 is a table cell.
    batch = _batch(
        [
            _seg("b0", "paragraph", [_icon(), _icon(), _xref(), _text("hi")]),
            _seg("c0", "table_cell", [_text("x")]),
        ]
    )
    score = classify_hardness(batch, cfg)
    assert score.features["icon_density"] == 1.0  # 2 icons / 2 segments
    assert score.features["xref_density"] == 0.5  # 1 xref / 2 segments
    assert score.features["table_ratio"] == 0.5  # 1 table cell / 2 segments
    assert score.features["segment_load"] == 2.0
    assert score.contributions["icon_density"] == 2.0  # 2.0 weight * 1.0
    assert score.contributions["xref_density"] == 0.5
    assert score.contributions["table_ratio"] == 0.25
    assert score.contributions["segment_load"] == 0.0
    assert score.score == 2.75


# ── Threshold boundary ────────────────────────────────────────────────


def test_score_exactly_at_threshold_is_hard() -> None:
    """``score == threshold`` routes hard (``>=`` boundary)."""
    # One paragraph, one icon → icon_density 1.0; only icon weight nonzero.
    batch = _batch([_seg("b0", "paragraph", [_icon(), _text("x")])])
    cfg = _default_cfg(
        threshold=1.0,
        weight_icon_density=1.0,
        weight_xref_density=0.0,
        weight_table_ratio=0.0,
        weight_segment_load=0.0,
    )
    score = classify_hardness(batch, cfg)
    assert score.score == 1.0
    assert score.is_hard is True


def test_score_just_below_threshold_is_not_hard() -> None:
    """A score below the threshold routes easy."""
    batch = _batch([_seg("b0", "paragraph", [_icon(), _text("x")])])
    cfg = _default_cfg(
        threshold=1.0001,
        weight_icon_density=1.0,
        weight_xref_density=0.0,
        weight_table_ratio=0.0,
        weight_segment_load=0.0,
    )
    score = classify_hardness(batch, cfg)
    assert score.score == 1.0
    assert score.is_hard is False


# ── Group markers must not inflate xref density ───────────────────────


def test_narrative_group_markers_excluded_from_xref_count() -> None:
    """Synthetic block-boundary markers are not counted as cross-references."""
    marker = XrefInline(target_section_id=f"{GROUP_MARKER_PREFIX}b0", label="paragraph")
    real = _xref("s.7")
    batch = _batch([_seg("g", "narrative_group", [marker, _text("prose"), real])])
    score = classify_hardness(batch, _default_cfg())
    assert score.signals.xref_count == 1  # only the real xref, not the marker


# ── Degenerate + determinism ──────────────────────────────────────────


def test_empty_batch_is_not_hard_and_does_not_divide_by_zero() -> None:
    """Zero segments → zero score, easy verdict, no ZeroDivisionError."""
    score = classify_hardness(_batch([]), _default_cfg())
    assert score.signals.segment_count == 0
    assert score.features["icon_density"] == 0.0
    assert score.score == 0.0
    assert score.is_hard is False


def test_classification_is_deterministic() -> None:
    """Two runs on the same batch produce identical metadata (AC 4)."""
    cells = [
        _seg(f"c{i}", "table_cell", [_icon(), _xref(f"s.{i}"), _text("cell")]) for i in range(3)
    ]
    batch = _batch(cells)
    a = classify_hardness(batch, _default_cfg()).to_metadata()
    b = classify_hardness(batch, _default_cfg()).to_metadata()
    assert a == b


def test_to_metadata_shape() -> None:
    """Metadata carries score, threshold, verdict, and full signal breakdown."""
    batch = _batch([_seg("b0", "paragraph", [_icon(), _text("hi")])])
    meta = classify_hardness(batch, _default_cfg()).to_metadata()
    assert set(meta) == {"score", "threshold", "is_hard", "features", "contributions", "signals"}
    features = meta["features"]
    signals = meta["signals"]
    assert isinstance(features, dict)
    assert isinstance(signals, dict)
    assert set(features) == {
        "icon_density",
        "xref_density",
        "table_ratio",
        "segment_load",
    }
    assert set(signals) == {
        "segment_count",
        "icon_count",
        "xref_count",
        "table_segment_count",
        "char_count",
    }
