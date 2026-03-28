"""Tests for conservative text normalization."""

from __future__ import annotations

from atr_pipeline.stages.structure.text_normalize import (
    normalize_text,
    normalize_text_inlines,
)
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import TextInline

# ── Dehyphenation ────────────────────────────────────────────────────


def test_dehyphenate_simple_word() -> None:
    assert normalize_text("some- thing") == "something"


def test_dehyphenate_multiple() -> None:
    assert normalize_text("knowl- edge and under- standing") == "knowledge and understanding"


def test_dehyphenate_preserves_well_known() -> None:
    assert normalize_text("well- known") == "well-known"


def test_dehyphenate_preserves_self_referential() -> None:
    assert normalize_text("self- referential") == "self-referential"


def test_dehyphenate_preserves_half_life() -> None:
    assert normalize_text("half- life") == "half-life"


def test_dehyphenate_preserves_co_op() -> None:
    assert normalize_text("co- op") == "co-op"


def test_dehyphenate_preserves_re_roll() -> None:
    assert normalize_text("re- roll") == "re-roll"


def test_real_hyphen_untouched() -> None:
    """In-word hyphens without a trailing space are not changed."""
    assert normalize_text("co-op") == "co-op"
    assert normalize_text("well-known") == "well-known"
    assert normalize_text("re-roll") == "re-roll"


def test_dehyphenate_case_insensitive_prefix() -> None:
    """Uppercase prefix still matches safelist."""
    assert normalize_text("Non- linear") == "Non-linear"


# ── Control-character cleanup ────────────────────────────────────────


def test_strip_bel() -> None:
    assert normalize_text("hello\x07world") == "helloworld"


def test_strip_mixed_control_chars() -> None:
    assert normalize_text("a\x00b\x01c\x02d") == "abcd"


def test_preserves_tab_and_newline() -> None:
    assert normalize_text("line\tone\nline two") == "line\tone\nline two"


# ── Glued sentence fix ──────────────────────────────────────────────


def test_fix_glued_period() -> None:
    assert normalize_text("end.Start") == "end. Start"


def test_fix_glued_exclamation() -> None:
    assert normalize_text("done!Next") == "done! Next"


def test_fix_glued_question() -> None:
    assert normalize_text("why?Because") == "why? Because"


def test_no_false_space_abbreviation() -> None:
    """U.S. must not gain a spurious space."""
    assert normalize_text("U.S.A.") == "U.S.A."


def test_no_false_space_digit_period() -> None:
    assert normalize_text("3.5") == "3.5"


def test_no_false_space_uppercase_period() -> None:
    """Period after uppercase does not trigger (e.g. acronym)."""
    assert normalize_text("U.N.") == "U.N."


# ── Combined ─────────────────────────────────────────────────────────


def test_combined_normalizations() -> None:
    text = "some- thing happened.Then\x07 more"
    assert normalize_text(text) == "something happened. Then more"


# ── normalize_text_inlines ───────────────────────────────────────────


def test_inlines_preserves_marks() -> None:
    inlines = [TextInline(text="some- thing", marks=["bold"], lang=LanguageCode.EN)]
    result = normalize_text_inlines(inlines)
    assert len(result) == 1
    assert result[0].text == "something"
    assert result[0].marks == ["bold"]
    assert result[0].lang == LanguageCode.EN


def test_inlines_unchanged_passthrough() -> None:
    """Clean text returns the same object (no unnecessary copy)."""
    inlines = [TextInline(text="clean text", lang=LanguageCode.EN)]
    result = normalize_text_inlines(inlines)
    assert result[0] is inlines[0]
