"""Pure classifier coverage for S5U-1555 hard-page routing."""

from __future__ import annotations

from atr_pipeline.config.translation_hardness import TranslationHardnessConfig
from atr_pipeline.stages.translation.hardness import classify_hardness
from atr_pipeline.stages.translation.planner import build_translation_batch
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import IconInline, PageIRV1, TableBlock, TextInline, XrefInline


def _table_page() -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            TableBlock(
                block_id="p0001.b001",
                children=[
                    IconInline(symbol_id="sym.fate"),
                    XrefInline(target_page_id="p0002", label="see page 2"),
                    TextInline(text="text", lang=LanguageCode.EN),
                ],
            )
        ],
        reading_order=["p0001.b001"],
    )


def test_classifier_reports_raw_signals_and_weighted_contributions() -> None:
    """Every required PageIR/batch signal has transparent arithmetic."""
    page = _table_page()
    batch = build_translation_batch(page)
    config = TranslationHardnessConfig(
        enabled=True,
        threshold=8.0,
        inline_icon_density_weight=3.0,
        cross_reference_density_weight=6.0,
        table_presence_weight=2.0,
        segment_count_weight=1.0,
        segment_length_weight=0.5,
    )

    assessment = classify_hardness(page, batch, config)

    assert assessment.signals == {
        "inline_icon_density": 1 / 3,
        "cross_reference_density": 1 / 3,
        "table_presence": 1.0,
        "segment_count": 1.0,
        "average_segment_length": 4.0,
    }
    assert assessment.contributions == {
        "inline_icon_density": 1.0,
        "cross_reference_density": 2.0,
        "table_presence": 2.0,
        "segment_count": 1.0,
        "average_segment_length": 2.0,
    }
    assert assessment.score == 8.0
    assert assessment.is_hard is True


def test_classifier_threshold_is_inclusive() -> None:
    """A score exactly on the configured boundary routes hard."""
    page = _table_page()
    batch = build_translation_batch(page)

    at_boundary = classify_hardness(
        page,
        batch,
        TranslationHardnessConfig(
            enabled=True,
            threshold=1.0,
            inline_icon_density_weight=0.0,
            cross_reference_density_weight=0.0,
            table_presence_weight=1.0,
            segment_count_weight=0.0,
            segment_length_weight=0.0,
        ),
    )
    above_boundary = classify_hardness(
        page,
        batch,
        TranslationHardnessConfig(
            enabled=True,
            threshold=1.000001,
            inline_icon_density_weight=0.0,
            cross_reference_density_weight=0.0,
            table_presence_weight=1.0,
            segment_count_weight=0.0,
            segment_length_weight=0.0,
        ),
    )

    assert at_boundary.score == 1.0
    assert at_boundary.is_hard is True
    assert above_boundary.score == 1.0
    assert above_boundary.is_hard is False


def test_classifier_is_reproducible_for_identical_inputs() -> None:
    """Pure scoring returns structurally equal results across calls."""
    page = _table_page()
    batch = build_translation_batch(page)
    config = TranslationHardnessConfig(enabled=True, threshold=1.0, table_presence_weight=1.0)

    assert classify_hardness(page, batch, config) == classify_hardness(page, batch, config)
