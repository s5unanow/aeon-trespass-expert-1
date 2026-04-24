"""S5U-735 — systemic invariant: every QA rule must emit the real
``document_id`` on every ``QARecordV1`` it produces, never the
``page_id``.

Pre-S5U-735, seven rules sourced ``QARecordV1.document_id`` from
``render_page.source_map.page_id`` (a page id like ``"p0042"``)
because ``RenderSourceMap`` did not carry a document id field at all.
Downstream consumers that group/join by ``document_id`` (review-pack,
metrics rollups, user-feedback ingest) saw page ids where document
ids were expected, and their per-document rollups silently misaligned.

This test walks ``get_all_rules()`` and, for every record a rule
emits on a crafted page that fires most rule kinds, asserts the
record's ``document_id`` equals the real document id — never the
page id. It is systemic by design: any rule added to the registry
in the future is automatically covered (it just has to fire on the
crafted context).

Red-before: at commit 677c8d4 (pre-fix), the schema had no
``RenderSourceMap.document_id`` so the rules could not read it, and
seven of them read ``source_map.page_id`` and stuffed that into
``QARecordV1.document_id``. The parametric loop below therefore
fails on the first broken rule.
"""

from __future__ import annotations

from atr_pipeline.stages.qa.registry import QAPageContext, get_all_rules
from atr_schemas.enums import LanguageCode
from atr_schemas.page_ir_v1 import (
    HeadingBlock,
    IconInline,
    PageIRV1,
    ParagraphBlock,
    TextInline,
)
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderIconInline,
    RenderPageMeta,
    RenderPageV1,
    RenderParagraphBlock,
    RenderSourceMap,
    RenderTableBlock,
    RenderTextInline,
)

_DOC_ID = "ato_core_v1_1"
_PAGE_ID = "p0042"


def _make_source_ir() -> PageIRV1:
    """EN IR that matches the render page one-for-one (icons parity for
    ``icon_count_rule``)."""
    return PageIRV1(
        document_id=_DOC_ID,
        page_id=_PAGE_ID,
        page_number=42,
        language=LanguageCode.EN,
        blocks=[
            HeadingBlock(
                block_id=f"{_PAGE_ID}.b001",
                level=2,
                children=[TextInline(text="Wounded card:BP deckAI deck")],
            ),
            ParagraphBlock(
                block_id=f"{_PAGE_ID}.b002",
                children=[
                    TextInline(text="Get 1 "),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Progress"),
                ],
            ),
        ],
    )


def _make_target_ir() -> PageIRV1:
    """RU IR — fully translated so ``untranslated_rule`` stays quiet."""
    return PageIRV1(
        document_id=_DOC_ID,
        page_id=_PAGE_ID,
        page_number=42,
        language=LanguageCode.RU,
        blocks=[
            HeadingBlock(
                block_id=f"{_PAGE_ID}.b001",
                level=2,
                children=[TextInline(text="Проверка")],
            ),
            ParagraphBlock(
                block_id=f"{_PAGE_ID}.b002",
                children=[
                    TextInline(text="Получите 1 "),
                    IconInline(symbol_id="sym.progress"),
                    TextInline(text=" Прогресс"),
                ],
            ),
        ],
    )


def _make_render() -> RenderPageV1:
    """Render page with a block per rule the seven-rule systemic regression
    touches, plus ``chart_title_merge`` (the S5U-705 precedent).

    Rules whose document_id used to leak via ``source_map.page_id``:

    - ``paragraph_length``: long paragraph (>1000 chars).
    - ``flat_table``: RenderTableBlock with 20+ flat inline children.
    - ``duplicate_content``: two consecutive near-identical paragraphs.
    - ``decorative_icon``: raw asset token in a paragraph.
    - ``glued_text``: Cyrillic case-transition glue.
    - ``dead_page_ref``: "p. 999" inline.
    - ``leaked_identifier``: "UNKNOWN" inline.
    - ``chart_title_merge``: heading with colon-glue pattern.
    """
    long_text = "привет " * 250  # ~1500 chars of Russian
    flat_cells = [RenderTextInline(text=f"cell {i}") for i in range(25)]
    dup_a = RenderParagraphBlock(
        id=f"{_PAGE_ID}.b_dup_a",
        children=[RenderTextInline(text="the same old text content repeats here")],
    )
    dup_b = RenderParagraphBlock(
        id=f"{_PAGE_ID}.b_dup_b",
        children=[RenderTextInline(text="the same old text content repeats here")],
    )
    return RenderPageV1(
        schema_version="render_page.v1",
        document_version="ru",
        presentation_mode="article",
        page=RenderPageMeta(id=_PAGE_ID, title="", source_page_number=42),
        blocks=[
            # chart_title_merge fires on colon-glue heading.
            RenderHeadingBlock(
                id=f"{_PAGE_ID}.b_title",
                level=2,
                children=[RenderTextInline(text="Wounded card:BP deckAI deck")],
            ),
            # paragraph_length fires on >1000 char block.
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b_long",
                children=[RenderTextInline(text=long_text)],
            ),
            # flat_table fires on 25 flat inlines, no RenderTableRowBlock.
            RenderTableBlock(id=f"{_PAGE_ID}.b_flat", children=flat_cells),
            # duplicate_content fires on the (dup_a, dup_b) pair.
            dup_a,
            dup_b,
            # decorative_icon fires on raw asset-token leak.
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b_deco",
                children=[RenderTextInline(text="See artifact AA1234 in the manual.")],
            ),
            # glued_text fires on Cyrillic case-transition glue.
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b_glue",
                children=[RenderTextInline(text="словоСЛОВО")],
            ),
            # dead_page_ref fires on "p. 999" (no manifest supplied, so all
            # references are treated as dead).
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b_ref",
                children=[RenderTextInline(text="See p. 999 for details.")],
            ),
            # leaked_identifier fires on "UNKNOWN".
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b_leak",
                children=[RenderTextInline(text="UNKNOWN placeholder left behind.")],
            ),
            # Icon-count parity block (quiet): matches source/target IR.
            RenderParagraphBlock(
                id=f"{_PAGE_ID}.b002",
                children=[
                    RenderTextInline(text="..."),
                    RenderIconInline(symbol_id="sym.progress"),
                    RenderTextInline(text="..."),
                ],
            ),
        ],
        source_map=RenderSourceMap(
            page_id=_PAGE_ID,
            document_id=_DOC_ID,
            block_refs=[],
        ),
    )


def _make_ctx() -> QAPageContext:
    return QAPageContext(
        source_ir=_make_source_ir(),
        target_ir=_make_target_ir(),
        render_page=_make_render(),
        known_page_numbers=None,
    )


def test_all_rules_emit_document_id_as_document_not_page() -> None:
    """Every record a registered rule emits must carry the real document
    id (``"ato_core_v1_1"``), never the page id (``"p0042"``).

    The test is parametric over ``get_all_rules()`` so any rule added
    in the future is covered automatically, provided the crafted
    context fires at least one of its codes.
    """
    ctx = _make_ctx()
    rules_that_fired: set[str] = set()

    for rule in get_all_rules():
        records = rule.evaluate(ctx)
        if records:
            rules_that_fired.add(rule.name)
        for record in records:
            assert record.document_id == _DOC_ID, (
                f"rule {rule.name!r} emitted record.document_id="
                f"{record.document_id!r} expected {_DOC_ID!r} — likely "
                "reading source_map.page_id again (S5U-735)"
            )
            assert record.document_id != record.page_id, (
                f"rule {rule.name!r} set document_id == page_id "
                f"({record.document_id!r}); document_id must be the "
                "parent document id, not the page id (S5U-735)"
            )

    # Guard against the silent-pass mode: if none of the crafted blocks
    # fire any rule, the loop trivially passes and the test gives a
    # false green. Require at least five of the eight known broken
    # rules (plus chart_title_merge) to have emitted records.
    expected_at_least = 5
    assert len(rules_that_fired) >= expected_at_least, (
        f"Only {len(rules_that_fired)} rules fired "
        f"({sorted(rules_that_fired)!r}); crafted context may have "
        "drifted — the invariant check is trivially passing. Expected "
        f"at least {expected_at_least} rules to fire."
    )
