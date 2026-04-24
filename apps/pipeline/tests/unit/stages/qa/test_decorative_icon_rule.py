"""Tests for decorative icon leakage QA rule."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.decorative_icon_rule import evaluate_decorative_icons
from atr_schemas.render_page_v1 import (
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTextInline,
)


def _page(blocks: list[RenderParagraphBlock]) -> RenderPageV1:
    return RenderPageV1(
        page=RenderPageMeta(id="p0001", title="Тест", source_page_number=1),
        blocks=blocks,
        source_map=RenderSourceMap(page_id="p0001", block_refs=[]),
    )


def _para(block_id: str, text: str) -> RenderParagraphBlock:
    return RenderParagraphBlock(
        id=block_id,
        children=[RenderTextInline(text=text)],
    )


def test_detects_raw_asset_token() -> None:
    """Two uppercase letters + four digits (AM0308) is flagged."""
    page = _page([_para("b1", "Используйте AM0308 для атаки")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 1
    assert records[0].code == "DECORATIVE_ICON_LEAKED"
    assert "AM0308" in records[0].message


def test_detects_stage_internal_code() -> None:
    """T##T## pattern is flagged."""
    page = _page([_para("b1", "Карта T01T00 в зоне")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 1
    assert "T01T00" in records[0].message


def test_detects_private_use_glyph() -> None:
    """Private-use Unicode character is flagged."""
    page = _page([_para("b1", "Текст \ue001 после")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 1
    assert "Private-use glyph" in records[0].message


def test_detects_placeholder_dot() -> None:
    """Isolated dot surrounded by spaces is flagged."""
    page = _page([_para("b1", "\u0441 помощью . получите")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 1
    assert "placeholder" in records[0].message.lower()


def test_detects_placeholder_alpha() -> None:
    """Isolated alpha is flagged."""
    page = _page([_para("b1", "Бросьте \u03b1 кубик")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 1
    assert "placeholder" in records[0].message.lower()


def test_ignores_clean_text() -> None:
    """Normal text without icon artifacts produces no records."""
    page = _page([_para("b1", "Получите 1 Прогресс.")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 0


def test_ignores_dot_in_sentence() -> None:
    """A period at end of sentence is not a placeholder."""
    page = _page([_para("b1", "Конец хода.")])
    records = evaluate_decorative_icons(page)

    assert len(records) == 0


def test_severity_is_warning() -> None:
    """Decorative icon leakage is WARNING severity."""
    page = _page([_para("b1", "Код AW0284 тут")])
    records = evaluate_decorative_icons(page)

    assert records[0].severity.value == "warning"


# --- S5U-701 — placeholder-prose detection -----------------------------------
#
# The Apr-22 EN bundle p0009.b026 ships the prose
#     "Potential symbol Power symbol ??? symbol"
# as visible body text — the PDF extractor dropped the actual icons and left
# descriptive stand-ins.  Never legitimate in game text ("the Potential", not
# "the Potential symbol").  The rule emits PLACEHOLDER_PROSE_LEAKED at ERROR
# severity so export refuses to publish while the extraction regression is
# being fixed upstream.


def test_detects_placeholder_prose_potential_symbol() -> None:
    """RED before fix — "<concept> symbol" prose is flagged."""
    page = _page([_para("b1", "Potential symbol Power symbol description")])
    records = evaluate_decorative_icons(page)

    placeholder = [r for r in records if r.code == "PLACEHOLDER_PROSE_LEAKED"]
    assert len(placeholder) == 1
    assert placeholder[0].entity_ref == "b1"


def test_detects_placeholder_prose_question_marks() -> None:
    """RED before fix — the "??? symbol" stand-in used for unknown icons."""
    page = _page([_para("b1", "Don't worry about the ??? symbol yet.")])
    records = evaluate_decorative_icons(page)

    placeholder = [r for r in records if r.code == "PLACEHOLDER_PROSE_LEAKED"]
    assert len(placeholder) == 1


def test_placeholder_prose_severity_is_error() -> None:
    """RED before fix — placeholder prose MUST be ERROR (blocking) per the
    Must-refuse clause of S5U-701."""
    page = _page([_para("b1", "Potential symbol appears")])
    records = evaluate_decorative_icons(page)

    placeholder = [r for r in records if r.code == "PLACEHOLDER_PROSE_LEAKED"]
    assert placeholder[0].severity.value == "error"


def test_placeholder_prose_ignores_legitimate_symbol_noun() -> None:
    """Adversarial — "symbol" used as a noun in legitimate prose
    (without "<concept> symbol" adjacency) is NOT flagged."""
    page = _page(
        [
            _para("b1", "The symbol on the card shows a hooded figure."),
            _para("b2", "This is a powerful symbol of victory."),
        ]
    )
    records = evaluate_decorative_icons(page)

    placeholder = [r for r in records if r.code == "PLACEHOLDER_PROSE_LEAKED"]
    assert placeholder == []
