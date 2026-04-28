"""S5U-745 — TermMarkInline / XrefInline render dispatch tests.

S5U-739 fixed the silent drop of ``FigureRefInline`` in
``_convert_inline_nodes``. Two IR inline types still fell through the
dispatch and were silently dropped: ``TermMarkInline`` and
``XrefInline``. This file pins the post-S5U-745 contract:

* ``TermMarkInline`` flattens to ``RenderTextInline(text=surface_form)``.
  ``GlossaryText`` already auto-highlights surface forms from the
  glossary registry on the reader side, so re-emitting the per-instance
  ``concept_id`` link metadata in the render payload would be redundant.
* ``XrefInline`` flattens to ``RenderTextInline(text=label)``. No
  producer exists in the pipeline today; this keeps the dispatch
  exhaustive until a future producer needs richer link semantics.
* The trailing ``typing.assert_never(node)`` makes the dispatch
  exhaustive at type-check time — adding a 7th IR inline variant
  without a render branch fails mypy --strict before merge.

Lives in a separate file from ``test_page_builder.py`` because that
file is in ``KNOWN_VIOLATORS`` (S5U-677) and must not grow.
"""

from __future__ import annotations

from atr_pipeline.stages.render.page_builder import build_render_page
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TermMarkInline,
    TextInline,
    XrefInline,
)

# ── TermMarkInline dispatch ─────────────────────────────────────────


def test_term_mark_inline_flattens_to_text() -> None:
    """S5U-745: a paragraph carrying a single ``TermMarkInline`` produces a
    ``RenderParagraphBlock`` with one ``RenderTextInline`` whose text is
    the IR node's ``surface_form``.

    Red-before confirmation: prior to the page_builder.py edit on this
    branch, ``_convert_inline_nodes`` had no ``TermMarkInline`` dispatch
    branch, so the term_mark fell through and the paragraph's children
    came back empty — ``len(children) == 1`` failed at ``assert 0 == 1``.
    Run on commit a43e4ba (the pre-fix tree, S5U-744 merge SHA): the
    assertion below fails because the dispatch silently drops the node.
    """
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0090",
        page_number=90,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0090.b001",
                children=[
                    TermMarkInline(concept_id="concept.cypher", surface_form="cypher"),
                ],
            ),
        ],
        reading_order=["p0090.b001"],
    )
    render = build_render_page(ir)

    assert len(render.blocks) == 1
    block = render.blocks[0]
    assert block.kind == "paragraph"
    children = block.children  # type: ignore[union-attr]
    assert len(children) == 1
    assert children[0].kind == "text"
    # Surface form round-trips as the visible text — concept_id is
    # intentionally not surfaced (GlossaryText highlights from the
    # registry on the reader, so the per-instance link metadata is
    # redundant in the render payload).
    assert children[0].text == "cypher"  # type: ignore[union-attr]


def test_term_mark_empty_surface_form_renders_empty_text() -> None:
    """S5U-745: when ``surface_form == ""``, the dispatch still emits a
    ``RenderTextInline`` (with empty text) rather than silently dropping
    the node.

    Pins the empty-string-input contract so future refactors cannot
    conflate "drop empty" with "drop term_mark." Adversarial scenario C
    in tmp/plan-s5u-745.md.

    Red-before confirmation: prior to the page_builder.py edit, the
    dispatch silently dropped every ``TermMarkInline`` regardless of
    surface_form, so ``len(children) == 1`` failed at ``assert 0 == 1``
    on commit a43e4ba.
    """
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0091",
        page_number=91,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0091.b001",
                children=[
                    TermMarkInline(concept_id="concept.cypher", surface_form=""),
                ],
            ),
        ],
        reading_order=["p0091.b001"],
    )
    render = build_render_page(ir)

    block = render.blocks[0]
    children = block.children  # type: ignore[union-attr]
    assert len(children) == 1
    assert children[0].kind == "text"
    assert children[0].text == ""  # type: ignore[union-attr]


def test_callout_mixes_term_mark_text_and_icon_preserves_order() -> None:
    """S5U-745: a CalloutBlock with mixed inline kinds preserves order
    after term_mark dispatch widens.

    The render order ``text -> term_mark -> icon -> text`` mirrors the
    IR order; the term_mark flattens to text in place. Surrounding text
    and icon nodes still convert to ``RenderTextInline`` and
    ``RenderIconInline`` respectively.

    Red-before confirmation: pre-fix on commit a43e4ba, the term_mark
    was silently dropped, so ``len(children)`` was 3 (text + icon + text)
    — the ``len(children) == 4`` assertion failed.
    """
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0092",
        page_number=92,
        language=LanguageCode.EN,
        blocks=[
            CalloutBlock(
                block_id="p0092.b001",
                variant="info",
                children=[
                    TextInline(text="see the ", lang=LanguageCode.EN),
                    TermMarkInline(concept_id="concept.cypher", surface_form="cypher"),
                    IconInline(symbol_id="sym.danger", instance_id="syminst.p0092.01"),
                    TextInline(text=" carefully.", lang=LanguageCode.EN),
                ],
            ),
        ],
        reading_order=["p0092.b001"],
    )
    render = build_render_page(ir)

    block = render.blocks[0]
    children = block.children  # type: ignore[union-attr]
    assert len(children) == 4
    assert [c.kind for c in children] == ["text", "text", "icon", "text"]
    assert children[0].text == "see the "  # type: ignore[union-attr]
    assert children[1].text == "cypher"  # type: ignore[union-attr]
    assert children[2].symbol_id == "sym.danger"  # type: ignore[union-attr]
    assert children[3].text == " carefully."  # type: ignore[union-attr]


# ── XrefInline dispatch ─────────────────────────────────────────────


def test_xref_inline_flattens_to_label_text() -> None:
    """S5U-745: a paragraph carrying an ``XrefInline`` produces a
    ``RenderParagraphBlock`` with one ``RenderTextInline`` carrying the
    IR node's ``label`` as its text.

    No producer exists in the pipeline today, but the dispatch must
    still be exhaustive — flattening to the visible label is strictly
    better than silently dropping the node, and lets a future producer
    decide between (a) accepting the flatten or (b) upgrading to a
    richer ``RenderXrefInline`` schema in a follow-up issue.

    Red-before confirmation: prior to the page_builder.py edit,
    ``_convert_inline_nodes`` had no ``XrefInline`` dispatch branch, so
    the xref fell through and the paragraph's children came back empty.
    On commit a43e4ba the assertion ``len(children) == 1`` failed at
    ``assert 0 == 1``.
    """
    ir = PageIRV1(
        document_id="test_doc",
        page_id="p0093",
        page_number=93,
        language=LanguageCode.EN,
        blocks=[
            ParagraphBlock(
                block_id="p0093.b001",
                children=[
                    XrefInline(
                        target_page_id="p0099",
                        target_section_id="sec.combat",
                        label="Combat Phase",
                    ),
                ],
            ),
        ],
        reading_order=["p0093.b001"],
    )
    render = build_render_page(ir)

    block = render.blocks[0]
    children = block.children  # type: ignore[union-attr]
    assert len(children) == 1
    assert children[0].kind == "text"
    assert children[0].text == "Combat Phase"  # type: ignore[union-attr]
