"""QA rule: detect glued (unseparated) text in rendered output."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

# Case transition: lowercase Cyrillic immediately followed by 2+ uppercase
_CASE_GLUE_RE = re.compile(r"[\u0430-\u044F\u0451][\u0410-\u042F\u0401]{2,}")

# Repeated phrase: 4+ char substring repeated back-to-back
_REPEAT_RE = re.compile(r"(.{4,})\1")

# Word-number glue: Cyrillic letter touching a digit
_WORD_NUM_RE = re.compile(
    r"[\u0410-\u042F\u0430-\u044F\u0401\u0451]\d"
    r"|\d[\u0410-\u042F\u0430-\u044F\u0401\u0451]"
)

# Punctuation glue: sentence-end punctuation directly followed by uppercase Cyrillic
_PUNCT_GLUE_RE = re.compile(r"[.!?][\u0410-\u042F\u0401]")

# Latin punctuation glue: lowercase Latin + sentence-end + uppercase Latin
_LATIN_PUNCT_GLUE_RE = re.compile(r"[a-z][.!?][A-Z]")


def _check_text(text: str) -> str | None:
    """Return a reason string if *text* contains glued content."""
    m = _CASE_GLUE_RE.search(text)
    if m:
        return f"Case transition glue: ...{m.group()}..."
    m = _REPEAT_RE.search(text)
    if m:
        return f"Repeated phrase: '{m.group(1)}' appears back-to-back"
    m = _PUNCT_GLUE_RE.search(text)
    if m:
        return f"Punctuation glue: '{m.group()}'"
    m = _WORD_NUM_RE.search(text)
    if m:
        return f"Word-number glue: '{m.group()}'"
    m = _LATIN_PUNCT_GLUE_RE.search(text)
    if m:
        return f"Latin punctuation glue: '{m.group()}'"
    return None


def evaluate_glued_text(render_page: RenderPageV1) -> list[QARecordV1]:
    """Scan a render page for glued text.

    Returns one QARecordV1 per affected block.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.page_id if render_page.source_map else ""

    for block in render_page.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        for child in block.children:
            if child.kind != "text":
                continue
            reason = _check_text(child.text)
            if reason:
                records.append(
                    QARecordV1(
                        qa_id=f"qa.{page_id}.glued_text.{block.id}",
                        layer=QALayer.EXTRACTION,
                        severity=Severity.WARNING,
                        code="GLUED_TEXT",
                        document_id=doc_id,
                        page_id=page_id,
                        entity_ref=block.id,
                        message=reason,
                    )
                )
                break  # one record per block

    return records
