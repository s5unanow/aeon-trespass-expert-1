"""Tests for untranslated text detection QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.untranslated_rule import evaluate_untranslated
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import PageIRV1, ParagraphBlock, TextInline


def _ir(text: str) -> PageIRV1:
    return PageIRV1(
        document_id="test",
        page_id="p0001",
        page_number=1,
        language=LanguageCode.RU,
        blocks=[ParagraphBlock(block_id="b1", children=[TextInline(text=text)])],
    )


# Build Cyrillic strings from Unicode escapes to avoid RUF001
_CYRILLIC_30 = "".join(chr(c) for c in [0x41F, 0x440, 0x438, 0x432, 0x435, 0x442]) * 5
_LATIN_30 = "Hello this is untranslated text"
_MIXED_MOSTLY_LATIN = "Hello world this is text " + "".join(chr(c) for c in [0x41F, 0x440, 0x438])
_MIXED_MOSTLY_CYRILLIC = (
    "".join(chr(c) for c in [0x41F, 0x440, 0x438, 0x432, 0x435, 0x442]) * 4 + " hi"
)


def test_flags_fully_latin_block() -> None:
    """Block with all Latin chars is flagged."""
    ir = _ir(_LATIN_30)
    records = evaluate_untranslated(ir)

    assert len(records) == 1
    assert records[0].code == "UNTRANSLATED_TEXT"


def test_passes_cyrillic_block() -> None:
    """Block with all Cyrillic chars passes."""
    ir = _ir(_CYRILLIC_30)
    records = evaluate_untranslated(ir)

    assert len(records) == 0


def test_flags_mostly_latin_mixed() -> None:
    """Mixed block with >50% Latin is flagged."""
    ir = _ir(_MIXED_MOSTLY_LATIN)
    records = evaluate_untranslated(ir)

    assert len(records) == 1


def test_passes_mostly_cyrillic_mixed() -> None:
    """Mixed block with <50% Latin passes."""
    ir = _ir(_MIXED_MOSTLY_CYRILLIC)
    records = evaluate_untranslated(ir)

    assert len(records) == 0


def test_skips_short_blocks() -> None:
    """Blocks under 20 chars are not checked."""
    ir = _ir("Short latin text")
    records = evaluate_untranslated(ir)

    assert len(records) == 0


def test_custom_min_chars() -> None:
    """Custom min_chars threshold works."""
    ir = _ir("abcdefghij")  # 10 chars, all Latin
    assert len(evaluate_untranslated(ir, min_chars=10)) == 1
    assert len(evaluate_untranslated(ir, min_chars=11)) == 0


def test_custom_latin_ratio() -> None:
    """Custom latin_ratio threshold works."""
    ir = _ir(_MIXED_MOSTLY_LATIN)
    # With a very high ratio, the mixed block should pass
    assert len(evaluate_untranslated(ir, latin_ratio=0.95)) == 0


def test_severity_is_error() -> None:
    ir = _ir(_LATIN_30)
    records = evaluate_untranslated(ir)

    assert records[0].severity.value == "error"


def test_layer_is_terminology() -> None:
    ir = _ir(_LATIN_30)
    records = evaluate_untranslated(ir)

    assert records[0].layer.value == "terminology"


def test_entity_ref_is_block_id() -> None:
    ir = _ir(_LATIN_30)
    records = evaluate_untranslated(ir)

    assert records[0].entity_ref == "b1"


def test_message_contains_ratio() -> None:
    ir = _ir(_LATIN_30)
    records = evaluate_untranslated(ir)

    assert "%" in records[0].message
