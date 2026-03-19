"""QA rule: flag overly long paragraphs in rendered output."""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

DEFAULT_MAX_CHARS = 1000


def evaluate_paragraph_length(
    render_page: RenderPageV1,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[QARecordV1]:
    """Flag render blocks whose combined text exceeds *max_chars*.

    Returns one QARecordV1 per offending block.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.page_id if render_page.source_map else ""

    for block in render_page.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        total = sum(len(child.text) for child in block.children if child.kind == "text")
        if total > max_chars:
            records.append(
                QARecordV1(
                    qa_id=f"qa.{page_id}.paragraph_length.{block.id}",
                    layer=QALayer.STRUCTURE,
                    severity=Severity.WARNING,
                    code="PARAGRAPH_TOO_LONG",
                    document_id=doc_id,
                    page_id=page_id,
                    entity_ref=block.id,
                    message=f"Block has {total} chars (max {max_chars})",
                    expected={"max_chars": max_chars},
                    actual={"chars": total},
                )
            )

    return records
