"""QA rule: detect dead PDF page references in rendered text."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

# Russian: "стр. 16", "стр.16", "стр 16"
_STR_RE = re.compile(r"\u0441\u0442\u0440\.?\s*\d+")

# English: "p. 16", "p.16"
_P_DOT_RE = re.compile(r"\bp\.\s*\d+", re.IGNORECASE)

# English: "page 16"
_PAGE_RE = re.compile(r"\bpage\s+\d+", re.IGNORECASE)


def _find_page_refs(text: str) -> str | None:
    """Return the first dead page reference found in *text*, or None."""
    for pattern in (_STR_RE, _P_DOT_RE, _PAGE_RE):
        m = pattern.search(text)
        if m:
            return m.group()
    return None


def evaluate_dead_page_refs(render_page: RenderPageV1) -> list[QARecordV1]:
    """Scan a render page for dead PDF page references.

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
            ref = _find_page_refs(child.text)
            if ref:
                records.append(
                    QARecordV1(
                        qa_id=f"qa.{page_id}.dead_page_ref.{block.id}",
                        layer=QALayer.RENDER,
                        severity=Severity.WARNING,
                        code="DEAD_PAGE_REF",
                        document_id=doc_id,
                        page_id=page_id,
                        entity_ref=block.id,
                        message=f"Dead page reference: '{ref}'",
                    )
                )
                break  # one record per block

    return records
