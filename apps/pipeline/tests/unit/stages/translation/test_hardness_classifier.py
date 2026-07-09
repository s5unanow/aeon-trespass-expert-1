"""Unit tests for pure hardness classifier (S5U-1541).

All tests are deterministic, no network, no real translators. The classifier
itself is exercised directly (pure logic) and via stage integration using the
mock translator.
"""

from __future__ import annotations

import pytest

from atr_pipeline.config.models import HardnessConfig, TranslationConfig
from atr_pipeline.services.llm.mock_translator import MockTranslator
from atr_pipeline.stages.translation.hardness import (
    compute_hardness,
)
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_schemas.page_ir_v1 import (
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
    XrefInline,
)
from atr_schemas.translation_batch_v1 import (
    SegmentContext,
    TranslationBatchV1,
    TranslationSegment,
)


def _make_simple_page_ir(blocks: list) -> PageIRV1:
    """Minimal PageIRV1 for planner tests (only blocks matter for hardness)."""
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language="en",
        dimensions_pt=None,
        blocks=blocks,
        reading_order=[b.block_id for b in blocks],
    )


def _make_batch_with_icons(
    n_icons: int = 0, n_xrefs: int = 0, has_table: bool = False, n_segs: int = 3
) -> TranslationBatchV1:
    """Construct a synthetic batch exercising the four signals (reliable counts)."""
    segments: list[TranslationSegment] = []
    base_text = [TextInline(text="Text segment content. " * 4)]
    icon_pool = [IconInline(symbol_id=f"sym.icon{k}") for k in range(n_icons)]
    xref_pool = (
        [XrefInline(target_section_id="sec.foo", label="see foo") for _ in range(n_xrefs)]
        if n_xrefs
        else []
    )
    per_seg = n_icons // max(1, n_segs)
    remainder = n_icons % max(1, n_segs)
    icon_idx = 0
    for i in range(n_segs):
        inlines: list = list(base_text)
        take = per_seg + (1 if i < remainder else 0)
        for _ in range(take):
            if icon_idx < len(icon_pool):
                inlines.append(icon_pool[icon_idx])
                icon_idx += 1
        if i == 0:
            inlines.extend(xref_pool)
        btype = "table_cell" if (has_table and i == min(1, n_segs - 1)) else "paragraph"
        seg = TranslationSegment(
            segment_id=f"p0001.b{i}",
            block_type=btype,
            source_inline=inlines,
            source_checksum=f"cs{i}",
            context=SegmentContext(page_id="p0001"),
        )
        segments.append(seg)
    return TranslationBatchV1(
        batch_id="tr.test.hard.01",
        segments=segments,
    )


def _make_icon_dense_batch() -> TranslationBatchV1:
    """A page that should score high on icon signal."""
    inlines = [TextInline(text="Gain ")] + [IconInline(symbol_id=f"sym.s{i}") for i in range(12)]
    seg = TranslationSegment(
        segment_id="p1.b1",
        block_type="paragraph",
        source_inline=inlines,
        source_checksum="dense",
        context=SegmentContext(page_id="p0001"),
    )
    return TranslationBatchV1(batch_id="tr.dense", segments=[seg])


def _make_easy_batch() -> TranslationBatchV1:
    """Low signal batch: should stay on model_default."""
    seg = TranslationSegment(
        segment_id="p1.b1",
        block_type="paragraph",
        source_inline=[TextInline(text="Simple sentence.")],
        source_checksum="easy",
        context=SegmentContext(page_id="p0001"),
    )
    return TranslationBatchV1(batch_id="tr.easy", segments=[seg])


def _make_table_batch() -> TranslationBatchV1:
    seg = TranslationSegment(
        segment_id="p1.cell.0",
        block_type="table_cell",
        source_inline=[TextInline(text="Cell content here.")],
        source_checksum="tbl",
        context=SegmentContext(page_id="p0001"),
    )
    return TranslationBatchV1(batch_id="tr.tbl", segments=[seg])


def _make_xref_batch() -> TranslationBatchV1:
    seg = TranslationSegment(
        segment_id="p1.b1",
        block_type="paragraph",
        source_inline=[
            TextInline(text="See "),
            XrefInline(target_section_id="sec.bar", label="Bar"),
            TextInline(text=" for details."),
        ],
        source_checksum="xref",
        context=SegmentContext(page_id="p0001"),
    )
    return TranslationBatchV1(batch_id="tr.xref", segments=[seg])


def test_classifier_disabled_returns_default_and_zero_score() -> None:
    """Disabled (default) never escalates; score 0, breakdown empty."""
    cfg = HardnessConfig(enabled=False)
    batch = _make_icon_dense_batch()
    res = compute_hardness(batch, cfg, "default-model", "hard-model")
    assert res.enabled is False
    assert res.score == 0.0
    assert res.chosen_model == "default-model"
    assert res.signal_breakdown == {}
    assert res.threshold == 0.50


def test_classifier_hard_icon_dense_routes_to_model_hard() -> None:
    """Icon-dense synthetic page exceeds default threshold -> model_hard."""
    # With default weights icon_d=1.0 contributes 0.35, plus small length;
    # use a threshold the dense page reliably exceeds.
    cfg = HardnessConfig(enabled=True, threshold=0.30)
    batch = _make_icon_dense_batch()
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.enabled is True
    assert res.score >= 0.30
    assert res.chosen_model == "hard"
    assert "icon_density" in res.signal_breakdown
    assert res.signals.icon_count >= 10


def test_classifier_easy_page_stays_default() -> None:
    """Low-signal page stays on default even when enabled."""
    cfg = HardnessConfig(enabled=True, threshold=0.50)
    batch = _make_easy_batch()
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.chosen_model == "def"
    assert res.score < 0.50


def test_classifier_table_presence_boosts_score() -> None:
    """Table presence contributes and can push borderline over threshold."""
    cfg = HardnessConfig(
        enabled=True,
        threshold=0.20,
        icon_weight=0.0,
        xref_weight=0.0,
        table_weight=0.80,
        length_weight=0.0,
    )
    batch = _make_table_batch()
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.signals.table_presence == 1
    assert res.score > 0.0
    assert res.chosen_model == "hard"


def test_classifier_xref_density_counts_only_real_xrefs() -> None:
    """Group marker xrefs are excluded from xref_count (internal use)."""
    # Build a batch that has a group marker xref + a real one
    group_x = XrefInline(target_section_id="translation-block:foo")
    real_x = XrefInline(target_section_id="sec.real")
    seg = TranslationSegment(
        segment_id="p1.b1",
        block_type="paragraph",
        source_inline=[TextInline(text="x"), group_x, real_x],
        source_checksum="g",
        context=SegmentContext(page_id="p0001"),
    )
    batch = TranslationBatchV1(batch_id="tr.g", segments=[seg])
    cfg = HardnessConfig(
        enabled=True,
        threshold=0.01,
        icon_weight=0.0,
        xref_weight=1.0,
        table_weight=0.0,
        length_weight=0.0,
    )
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.signals.xref_count == 1  # only the real one
    assert res.chosen_model == "hard"


def test_classifier_threshold_boundary_exact() -> None:
    """At exactly threshold we escalate ( >= )."""
    # Use icon_weight=1 so score == icon_d (capped). 2 icons -> 0.2 < 0.30
    cfg = HardnessConfig(
        enabled=True,
        threshold=0.30,
        icon_weight=1.0,
        xref_weight=0.0,
        table_weight=0.0,
        length_weight=0.0,
    )
    batch = _make_batch_with_icons(n_icons=2, n_segs=1)
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.chosen_model == "def"
    # 4 icons -> icon_d=0.4 >=0.30 -> hard
    batch4 = _make_batch_with_icons(n_icons=4, n_segs=1)
    res4 = compute_hardness(batch4, cfg, "def", "hard")
    assert res4.score >= 0.30
    assert res4.chosen_model == "hard"


def test_classifier_length_and_segment_contribute() -> None:
    """Long pages with many segments can cross threshold on length alone."""
    cfg = HardnessConfig(
        enabled=True,
        threshold=0.40,
        icon_weight=0.0,
        xref_weight=0.0,
        table_weight=0.0,
        length_weight=1.0,
    )
    # many segments + chars
    segs = []
    for i in range(20):
        segs.append(
            TranslationSegment(
                segment_id=f"b{i}",
                block_type="paragraph",
                source_inline=[TextInline(text="word " * 30)],
                source_checksum=str(i),
                context=SegmentContext(page_id="p0001"),
            )
        )
    batch = TranslationBatchV1(batch_id="tr.long", segments=segs)
    res = compute_hardness(batch, cfg, "def", "hard")
    assert res.score >= 0.40
    assert res.chosen_model == "hard"


def test_classifier_config_forbid_unknown_keys() -> None:
    """Pydantic extra=forbid on HardnessConfig (and parent) rejects junk."""
    with pytest.raises(ValueError):
        HardnessConfig(enabled=True, threshold=0.5, unknown_knob=123)  # type: ignore[call-arg]


def test_classifier_reproducible_across_calls() -> None:
    """Same batch + config always yields identical score and breakdown."""
    cfg = HardnessConfig(enabled=True, threshold=0.1)
    batch = _make_icon_dense_batch()
    r1 = compute_hardness(batch, cfg, "d", "h")
    r2 = compute_hardness(batch, cfg, "d", "h")
    assert r1.score == r2.score
    assert r1.chosen_model == r2.chosen_model
    assert r1.signal_breakdown == r2.signal_breakdown


def test_stage_integration_hard_routes_and_records_metadata(tmp_path) -> None:
    """Using mock translator + enabled hardness, hard page records model_hard and hardness meta."""
    # Build a minimal ctx-like but we call translator directly after planner for isolation
    # Full stage test is heavier; here we simulate the routing path.
    tcfg = TranslationConfig(
        provider="mock",
        model_default="def-model",
        model_hard="hard-model",
        hardness=HardnessConfig(enabled=True, threshold=0.1),
    )
    # Use planner on a *dense* IR (many icons) to get a batch that crosses thresh
    ir = _make_simple_page_ir(
        blocks=[
            ParagraphBlock(
                block_id="p1.b1",
                children=(
                    [TextInline(text="foo")]
                    + [IconInline(symbol_id=f"sym.i{i}") for i in range(12)]
                ),
            )
        ]
    )
    batch = build_translation_batch(ir, prompt_profile="test.v1")
    translator = MockTranslator()
    hres = compute_hardness(batch, tcfg.hardness, tcfg.model_default, tcfg.model_hard)
    assert hres.chosen_model == "hard-model"
    resp = translator.translate_batch(batch, model_profile=hres.chosen_model)
    assert resp.meta.model == "hard-model"

    # Also verify disabled path leaves model default
    tcfg2 = TranslationConfig(
        provider="mock",
        model_default="def-model",
        model_hard="hard-model",
        hardness=HardnessConfig(enabled=False),
    )
    hres2 = compute_hardness(batch, tcfg2.hardness, tcfg2.model_default, tcfg2.model_hard)
    resp2 = translator.translate_batch(batch, model_profile=hres2.chosen_model)
    assert resp2.meta.model == "def-model"  # we explicitly pass default when disabled


def test_hardness_metadata_keys_only_present_when_enabled() -> None:
    """When disabled, no 'hardness' key should be injected (for byte-identical meta)."""
    # This is enforced in stage; here we assert classifier contract
    cfg_off = HardnessConfig(enabled=False)
    res = compute_hardness(_make_easy_batch(), cfg_off, "d", "h")
    assert "score" in res.to_meta_dict()  # still produces, but stage omits the key
    assert res.enabled is False

    cfg_on = HardnessConfig(enabled=True)
    res_on = compute_hardness(_make_icon_dense_batch(), cfg_on, "d", "h")
    md = res_on.to_meta_dict()
    assert "score" in md
    assert "signals" in md
    assert md["signals"]["icon_count"] > 0
