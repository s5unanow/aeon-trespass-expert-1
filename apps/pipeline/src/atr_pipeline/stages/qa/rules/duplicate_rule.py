"""QA rule: detect duplicate/near-duplicate consecutive blocks."""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderBlock, RenderDividerBlock, RenderPageV1

DEFAULT_JACCARD_THRESHOLD = 0.9


def _extract_text(block: RenderBlock) -> str:
    """Concatenate text children of a render block."""
    if isinstance(block, RenderDividerBlock):
        return ""
    return "".join(child.text for child in block.children if child.kind == "text")


def _word_set(text: str) -> set[str]:
    """Split text into a set of lowercase words."""
    return set(text.lower().split())


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two word sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate_duplicate_content(
    render_page: RenderPageV1,
    *,
    threshold: float = DEFAULT_JACCARD_THRESHOLD,
) -> list[QARecordV1]:
    """Flag consecutive blocks with near-identical text.

    Returns one QARecordV1 per duplicate pair (on the second block).
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.page_id if render_page.source_map else ""

    non_divider = [b for b in render_page.blocks if not isinstance(b, RenderDividerBlock)]

    prev_words: set[str] = set()
    prev_text = ""
    prev_id = ""

    for block in non_divider:
        text = _extract_text(block)
        words = _word_set(text)

        if prev_text and text and _jaccard(prev_words, words) > threshold:
            records.append(
                QARecordV1(
                    qa_id=f"qa.{page_id}.duplicate.{block.id}",
                    layer=QALayer.STRUCTURE,
                    severity=Severity.WARNING,
                    code="DUPLICATE_CONTENT",
                    document_id=doc_id,
                    page_id=page_id,
                    entity_ref=block.id,
                    message=f"Near-duplicate of preceding block {prev_id}",
                )
            )

        prev_words = words
        prev_text = text
        prev_id = block.id

    return records
