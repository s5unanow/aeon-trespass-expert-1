"""Tests for glued text detection QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.glued_text_rule import evaluate_glued_text
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _page(blocks: list[RenderParagraphBlock]) -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title="Test", source_page_number=1),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _para(block_id: str, text: str) -> RenderParagraphBlock:
    return RenderParagraphBlock(
        id=block_id,
        children=[RenderTextInline(text=text)],
    )


# Build test strings from Unicode escapes to avoid RUF001/RUF003
_CASE_GLUE = "".join(chr(c) for c in [0x44D, 0x442, 0x43E, 0x433, 0x43E, 0x2E, 0x41E, 0x421, 0x41A])
_REPEAT = "".join(chr(c) for c in [0x422, 0x420, 0x410, 0x412, 0x41C, 0x410]) * 2
_WORD_NUM = "".join(chr(c) for c in [0x41C, 0x43E, 0x439, 0x440, 0x43E, 0x441]) + "10"
_CLEAN = "".join(chr(c) for c in [0x41F, 0x43E, 0x43B, 0x443, 0x447, 0x438, 0x442, 0x435]) + " 1."
_END_OK = (
    "".join(chr(c) for c in [0x41A, 0x43E, 0x43D, 0x435, 0x446])
    + ". "
    + "".join(chr(c) for c in [0x41D, 0x430, 0x447, 0x430, 0x43B, 0x43E])
)


def test_detects_case_transition_glue() -> None:
    """Lowercase Cyrillic followed by 2+ uppercase is flagged."""
    page = _page([_para("b1", _CASE_GLUE)])
    records = evaluate_glued_text(page)

    assert len(records) == 1
    assert records[0].code == "GLUED_TEXT"


def test_detects_repeated_phrase() -> None:
    """Back-to-back repeated substring >= 4 chars is flagged."""
    page = _page([_para("b1", _REPEAT)])
    records = evaluate_glued_text(page)

    assert len(records) == 1
    assert "Repeated phrase" in records[0].message


def test_detects_word_number_glue() -> None:
    """Cyrillic letter touching a digit is flagged."""
    page = _page([_para("b1", _WORD_NUM)])
    records = evaluate_glued_text(page)

    assert len(records) == 1
    assert "Word-number glue" in records[0].message


def test_detects_punctuation_glue() -> None:
    """Period directly followed by uppercase Cyrillic is flagged."""
    page = _page([_para("b1", _CASE_GLUE)])
    records = evaluate_glued_text(page)

    assert len(records) >= 1
    assert records[0].code == "GLUED_TEXT"


def test_ignores_clean_text() -> None:
    """Normal spaced text produces no records."""
    page = _page([_para("b1", _CLEAN)])
    records = evaluate_glued_text(page)

    assert len(records) == 0


def test_ignores_normal_sentence_end() -> None:
    """Period followed by space and uppercase is not flagged."""
    page = _page([_para("b1", _END_OK)])
    records = evaluate_glued_text(page)

    assert len(records) == 0


def test_severity_is_warning() -> None:
    """Glued text is WARNING severity."""
    page = _page([_para("b1", _REPEAT)])
    records = evaluate_glued_text(page)

    assert records[0].severity.value == "warning"


def test_layer_is_extraction() -> None:
    """Glued text issues are in the EXTRACTION layer."""
    page = _page([_para("b1", _REPEAT)])
    records = evaluate_glued_text(page)

    assert records[0].layer.value == "extraction"
