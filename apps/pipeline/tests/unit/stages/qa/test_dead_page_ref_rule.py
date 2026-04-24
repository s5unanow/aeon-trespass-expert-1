"""Tests for dead PDF page reference QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.dead_page_ref_rule import evaluate_dead_page_refs
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


# Build Russian "стр. 16" from Unicode escapes to avoid RUF001
_STR_DOT_16 = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + ". 16"
_STR_NO_DOT = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + " 35"
_STR_NO_SPACE = "".join(chr(c) for c in [0x441, 0x442, 0x440]) + ".16"
# "см. стр. 16"
_SM_STR = "".join(chr(c) for c in [0x441, 0x43C]) + ". " + _STR_DOT_16


def test_detects_russian_page_ref_with_dot() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1
    assert records[0].code == "DEAD_PAGE_REF"


def test_detects_russian_page_ref_without_dot() -> None:
    page = _page([_para("b1", _STR_NO_DOT)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_russian_page_ref_no_space() -> None:
    page = _page([_para("b1", _STR_NO_SPACE)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_embedded_russian_ref() -> None:
    page = _page([_para("b1", _SM_STR)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_english_p_dot() -> None:
    page = _page([_para("b1", "see p. 42 for details")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_detects_english_page() -> None:
    page = _page([_para("b1", "refer to page 10")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_english_page_case_insensitive() -> None:
    page = _page([_para("b1", "see Page 5")])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_passes_clean_text() -> None:
    clean = "".join(chr(c) for c in [0x41F, 0x440, 0x438, 0x432, 0x435, 0x442]) + " 123"
    page = _page([_para("b1", clean)])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 0


def test_one_record_per_block() -> None:
    """Multiple refs in one block produce only one record."""
    text = _STR_DOT_16 + " and " + _STR_NO_DOT
    block = RenderParagraphBlock(
        id="b1",
        children=[
            RenderTextInline(text=text),
        ],
    )
    page = _page([block])
    records = evaluate_dead_page_refs(page)

    assert len(records) == 1


def test_severity_is_warning() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].severity.value == "warning"


def test_layer_is_render() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].layer.value == "render"


def test_entity_ref_is_block_id() -> None:
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page)

    assert records[0].entity_ref == "b1"


# --- S5U-701 — manifest-aware dead page ref -----------------------------------
#
# Pre-fix the rule never consulted the manifest and emitted a DEAD_PAGE_REF
# record for every "p. N" / "page N" / Russian-stran reference in page text.
# The Apr-22 EN bundle ships 177 such records on p0008..p0083, most of which
# cite targets that DO exist in the manifest (e.g. "p. 60" -> p0060 is
# published).  The fix threads the set of known published page numbers through
# QAPageContext; when the target is in the set, the finding is suppressed.


def test_dead_page_ref_suppressed_when_target_in_manifest() -> None:
    """RED before fix — the rule must consult the manifest and suppress
    page refs whose target IS in the published page-number set.

    This is the p0008 "see Ability Usage (p. 60)" case from S5U-701:
    p0060 is a real published page so this finding is a false positive.
    """
    page = _page([_para("b1", "see Ability Usage (p. 60) for details")])
    records = evaluate_dead_page_refs(page, known_page_numbers=frozenset({60}))

    assert records == []


def test_dead_page_ref_fires_when_target_missing_from_manifest() -> None:
    """Legitimate finding — "p. 999" target is not in the manifest so the
    rule still emits.  Paired with the suppression test above to confirm
    the rule distinguishes the two cases."""
    page = _page([_para("b1", "see legend (p. 999) for details")])
    records = evaluate_dead_page_refs(page, known_page_numbers=frozenset({1, 60}))

    assert len(records) == 1
    assert records[0].code == "DEAD_PAGE_REF"
    assert "p. 999" in records[0].message


def test_dead_page_ref_legacy_behavior_when_page_set_unknown() -> None:
    """When the known-page-number set is not supplied, the rule preserves
    its legacy all-refs-are-suspect behavior.  This is the fail-open-safe
    carve-out for contexts that cannot enumerate the page set (e.g. unit
    tests of a single rendered page, ad-hoc CLI invocation)."""
    page = _page([_para("b1", "see (p. 42) for details")])
    records = evaluate_dead_page_refs(page)  # no known_page_numbers

    assert len(records) == 1
    assert records[0].code == "DEAD_PAGE_REF"


def test_dead_page_ref_trailing_punctuation_extracts_digits() -> None:
    """Adversarial — "p. 60." and "p. 60)" extract the digits 60 correctly
    and are suppressed when 60 is in the manifest."""
    page = _page(
        [
            _para("b1", "see Ability Usage (p. 60)."),
            _para("b2", "compare p. 60, and p. 999 differs."),
        ]
    )
    records = evaluate_dead_page_refs(page, known_page_numbers=frozenset({60}))

    # b1 is fully covered (only p. 60); b2 still emits because p. 999 is not
    # in the set (rule fires on the first dead ref per block).
    codes = [r.entity_ref for r in records]
    assert "b1" not in codes
    assert "b2" in codes


def test_dead_page_ref_russian_ref_suppressed_when_in_manifest() -> None:
    """The Russian "стр. N" surface participates in manifest-awareness."""
    page = _page([_para("b1", _STR_DOT_16)])
    records = evaluate_dead_page_refs(page, known_page_numbers=frozenset({16}))

    assert records == []
