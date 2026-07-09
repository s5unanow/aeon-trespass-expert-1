"""S5U-1543 hardness classifier unit tests."""

from __future__ import annotations

import pytest

from atr_pipeline.config.models import TranslationHardnessConfig
from atr_pipeline.config.translation_hardness import TranslationHardnessWeights
from atr_pipeline.stages.translation.hardness import assess_translation_hardness
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TableBlock,
    TextInline,
    XrefInline,
)
from atr_schemas.translation_batch_v1 import TranslationBatchV1, TranslationSegment


def _batch(*segments: TranslationSegment) -> TranslationBatchV1:
    return TranslationBatchV1(batch_id="tr.p0001.01", segments=list(segments))


def _segment(segment_id: str, text: str) -> TranslationSegment:
    return TranslationSegment(
        segment_id=segment_id,
        block_type="paragraph",
        source_inline=[TextInline(text=text, lang=LanguageCode.EN)],
    )


def test_hardness_score_is_weighted_signal_sum() -> None:
    """Score and signal contributions are deterministic weighted values."""
    page = PageIRV1(
        document_id="doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="Gain", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.fate"),
                    IconInline(symbol_id="sym.danger"),
                    XrefInline(target_section_id="combat", label="Combat"),
                ],
            ),
            TableBlock(block_id="p0001.t001", translatable=False),
        ],
        reading_order=["p0001.b001", "p0001.t001"],
    )
    config = TranslationHardnessConfig(
        enabled=True,
        threshold=10.0,
        icon_density_reference=0.5,
        xref_density_reference=0.25,
        segment_count_reference=4,
        segment_length_reference=8,
        weights=TranslationHardnessWeights(
            inline_icon_density=2.0,
            cross_reference_density=3.0,
            table_presence=5.0,
            segment_count=0.5,
            segment_length=0.25,
        ),
    )

    result = assess_translation_hardness(
        page,
        _batch(_segment("p0001.b001", "Gain"), _segment("p0001.b002", "Pass")),
        config,
    )

    assert result.score == pytest.approx(10.375)
    assert result.is_hard is True
    assert result.signals["inline_icon_density"].raw_value == pytest.approx(0.5)
    assert result.signals["inline_icon_density"].contribution == pytest.approx(2.0)
    assert result.signals["cross_reference_density"].raw_value == pytest.approx(0.25)
    assert result.signals["cross_reference_density"].contribution == pytest.approx(3.0)
    assert result.signals["table_presence"].raw_value == pytest.approx(1.0)
    assert result.signals["table_presence"].contribution == pytest.approx(5.0)
    assert result.signals["segment_count"].raw_value == pytest.approx(2.0)
    assert result.signals["segment_count"].contribution == pytest.approx(0.25)
    assert result.signals["segment_length"].raw_value == pytest.approx(4.0)
    assert result.signals["segment_length"].contribution == pytest.approx(0.125)


def test_threshold_boundary_is_hard_at_exact_threshold() -> None:
    """A score equal to the configured threshold is routed as hard."""
    page = PageIRV1(
        document_id="doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="Gain", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.fate"),
                ],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    config = TranslationHardnessConfig(
        enabled=True,
        threshold=1.0,
        icon_density_reference=0.5,
        weights=TranslationHardnessWeights(
            inline_icon_density=1.0,
            segment_count=0.0,
            segment_length=0.0,
        ),
    )

    result = assess_translation_hardness(page, _batch(_segment("p0001.b001", "Gain")), config)

    assert result.score == pytest.approx(1.0)
    assert result.is_hard is True


def test_threshold_boundary_below_threshold_is_not_hard() -> None:
    """A score below the configured threshold stays on the default model."""
    page = PageIRV1(
        document_id="doc",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0001.b001",
                children=[
                    TextInline(text="Gain", lang=LanguageCode.EN),
                    IconInline(symbol_id="sym.fate"),
                ],
            ),
        ],
        reading_order=["p0001.b001"],
    )
    config = TranslationHardnessConfig(
        enabled=True,
        threshold=1.001,
        icon_density_reference=0.5,
        weights=TranslationHardnessWeights(
            inline_icon_density=1.0,
            segment_count=0.0,
            segment_length=0.0,
        ),
    )

    result = assess_translation_hardness(page, _batch(_segment("p0001.b001", "Gain")), config)

    assert result.score == pytest.approx(1.0)
    assert result.is_hard is False
