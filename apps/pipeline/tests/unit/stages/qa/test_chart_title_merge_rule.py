"""Tests for the chart_title_merge QA rule (S5U-698)."""

from __future__ import annotations

from atr_pipeline.stages.qa.rules.chart_title_merge_rule import (
    evaluate_chart_title_merge,
)
from atr_schemas.enums import QALayer, Severity
from atr_schemas.render_page_v1 import (
    RenderHeadingBlock,
    RenderPageMeta,
    RenderPageV1,
    RenderSourceMap,
    RenderTableBlock,
    RenderTextInline,
)


def _page(blocks: list, *, document_id: str = "walking_skeleton") -> RenderPageV1:
    return RenderPageV1(
        schema_version="render_page.v1",
        document_version="en",
        presentation_mode="article",
        page=RenderPageMeta(id="p0054", title=""),
        blocks=blocks,
        source_map=RenderSourceMap(document_id=document_id, page_id="p0054"),
    )


def test_glued_chart_heading_emits_error_record() -> None:
    """p0054 regression — a heading containing the colon-glue pattern
    ``":B"`` emits an ERROR-severity QA record with code ``CHART_TITLE_MERGE``.
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0054.b001",
                level=2,
                children=[RenderTextInline(text="Wounded card:BP deckAI deck")],
            ),
        ]
    )
    records = evaluate_chart_title_merge(page)
    assert len(records) == 1
    rec = records[0]
    assert rec.code == "CHART_TITLE_MERGE"
    assert rec.severity == Severity.ERROR
    assert rec.layer == QALayer.STRUCTURE
    assert rec.entity_ref == "p0054.b001"


def test_case_transition_glue_emits_record() -> None:
    """Case-transition glue (``deckAI``) alone is enough to fire the rule,
    even without colon-glue.
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0042.b001",
                level=2,
                children=[RenderTextInline(text="final turnAI turn")],
            ),
        ]
    )
    records = evaluate_chart_title_merge(page)
    assert len(records) == 1
    assert records[0].code == "CHART_TITLE_MERGE"


def test_clean_heading_emits_no_record() -> None:
    """Happy path — a legitimate heading without glue patterns emits no record.
    Covers the must-not-break bullet that ordinary article pages keep correct
    title selection.
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0001.b001",
                level=1,
                children=[RenderTextInline(text="Attack Phase")],
            ),
            RenderHeadingBlock(
                id="p0001.b002",
                level=2,
                children=[RenderTextInline(text="Chapter 1: Setup")],
            ),
        ]
    )
    records = evaluate_chart_title_merge(page)
    assert records == []


def test_glued_pattern_inside_table_body_is_ignored() -> None:
    """Adversarial — table-body blocks often contain case-transition-like
    text fragments because inline concatenation in TableBlock children is a
    known schema limitation. Only heading blocks are scanned; table blocks
    are deliberately out of scope (covered by the separate glued_text rule
    at the body layer).
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0054.b001",
                level=2,
                children=[RenderTextInline(text="Wounded / Escalation Charts")],
            ),
            RenderTableBlock(
                id="p0054.b002",
                children=[RenderTextInline(text="BP III deckAI deck discard")],
            ),
        ]
    )
    records = evaluate_chart_title_merge(page)
    assert records == []


def test_legitimate_camelcase_does_not_emit_record() -> None:
    """Adversarial — legitimate CamelCase words (``iPhone``, ``McDonald``) do
    not match the case-transition regex because the pattern requires two
    consecutive uppercase letters after a lowercase.
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0100.b001",
                level=1,
                children=[RenderTextInline(text="iPhone Features")],
            ),
            RenderHeadingBlock(
                id="p0100.b002",
                level=1,
                children=[RenderTextInline(text="McDonald Discussion")],
            ),
        ]
    )
    records = evaluate_chart_title_merge(page)
    assert records == []


def test_record_document_id_is_the_source_map_document_id_not_page_id() -> None:
    """S5U-705 → S5U-735 regression — ``QARecordV1.document_id`` must be
    the document id carried by ``render_page.source_map.document_id``
    (populated by the render stage from ``page_ir.document_id``), NOT
    the ``source_map.page_id`` value that the S5U-698 introduction
    erroneously used.

    S5U-705 landed the fix rule-locally via a ``document_id`` parameter.
    S5U-735 hoists it to a schema field so all QA rules read the same
    source. This test asserts the post-S5U-735 contract: the emitted
    record's ``document_id`` is whatever ``source_map.document_id`` was
    set to, and is NOT equal to the page id.
    """
    page = _page(
        [
            RenderHeadingBlock(
                id="p0054.b001",
                level=2,
                children=[RenderTextInline(text="Wounded card:BP deckAI deck")],
            ),
        ],
        document_id="ato_core_v1_1",
    )
    records = evaluate_chart_title_merge(page)
    assert len(records) == 1
    rec = records[0]
    # Positive assertion — the doc id threaded through is exactly what
    # source_map.document_id was set to.
    assert rec.document_id == "ato_core_v1_1"
    # Negative assertion — guards against the page_id-shaped value the
    # pre-fix code produced. ``p0054`` would pass the positive branch if
    # someone re-introduced the old fallback, so we also require the
    # field to NOT equal the page id.
    assert rec.document_id != rec.page_id
    assert rec.page_id == "p0054"
