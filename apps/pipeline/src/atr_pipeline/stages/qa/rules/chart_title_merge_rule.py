"""QA rule: detect collapsed chart/table headers that merged into a heading.

S5U-698 — a heading block whose text contains glued-cell signatures
(``:X`` with no space, ``xABC`` case-transition) almost always comes from
a multi-cell table-header row whose spans were concatenated without cell
boundaries in structure recovery. The user-visible symptom is a garbage
heading such as ``"Wounded card:BP deckAI deck"`` on p0054. This rule
emits an ERROR-severity record that surfaces the condition to QA so the
release cannot silently ship a misleading page (must-refuse semantics per
the Linear issue).
"""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderHeadingBlock, RenderPageV1

# Matches ``":X"`` with an uppercase letter glued right after the colon —
# "Wounded card:BP" / "A:B" — versus legitimate "Chapter 1: Setup" (space).
_COLON_GLUE_RE = re.compile(r":[A-Z]")

# Matches ``"xAB"`` where a lowercase ASCII letter is followed by two or
# more uppercase ASCII letters — "deckAI" — but not "iPhone" (single
# uppercase) or Cyrillic mid-case forms.
_CASE_GLUE_RE = re.compile(r"[a-z][A-Z]{2,}")


def _check_heading_text(text: str) -> str | None:
    """Return a reason string if *text* shows a merged-cell signature."""
    m = _COLON_GLUE_RE.search(text)
    if m:
        return f"Colon-glue (no space after colon): '{m.group()}'"
    m = _CASE_GLUE_RE.search(text)
    if m:
        return f"Case-transition glue (lower→UPPER run): '{m.group()}'"
    return None


def evaluate_chart_title_merge(render_page: RenderPageV1) -> list[QARecordV1]:
    """Flag heading blocks whose text shows a merged-cell pattern.

    Only heading blocks are scanned — table-body blocks routinely contain
    glue-like patterns in inline text and are out of scope for this rule
    (the ``glued_text`` rule covers body-text cases in a different layer).

    ``document_id`` is sourced from ``render_page.source_map.document_id``
    (populated by the render stage from ``page_ir.document_id``). Before
    S5U-735 it lived on a rule-local caller argument (S5U-705 hot-fix) and
    before that was erroneously read from ``render_page.source_map.page_id``
    (S5U-698), which is a page id, not a document id.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    document_id = render_page.source_map.document_id if render_page.source_map else ""

    for block in render_page.blocks:
        if not isinstance(block, RenderHeadingBlock):
            continue
        heading_text = "".join(child.text for child in block.children if child.kind == "text")
        reason = _check_heading_text(heading_text)
        if reason:
            records.append(
                QARecordV1(
                    qa_id=f"qa.{page_id}.chart_title_merge.{block.id}",
                    layer=QALayer.STRUCTURE,
                    severity=Severity.ERROR,
                    code="CHART_TITLE_MERGE",
                    document_id=document_id,
                    page_id=page_id,
                    entity_ref=block.id,
                    message=(
                        f"Heading text shows merged-cell signature — "
                        f"{reason}. Likely a multi-column table header "
                        "was concatenated during structure recovery."
                    ),
                )
            )

    return records
