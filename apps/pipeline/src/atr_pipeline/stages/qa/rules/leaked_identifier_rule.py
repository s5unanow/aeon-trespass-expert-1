"""QA rule: detect technical identifiers leaking into rendered text."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

# Document-ID pattern: snake_case ending with _v<digits> (e.g. ato_core_v1_1)
_DOC_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*_v\d+(?:_\d+)?")

# Standalone UNKNOWN (word boundary)
_UNKNOWN_RE = re.compile(r"\bUNKNOWN\b")

# Snake-case token with ≥3 segments in otherwise Cyrillic text
_SNAKE_3_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+){2,}")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")


def _check_text(text: str) -> str | None:
    """Return a reason string if *text* contains a leaked identifier."""
    m = _DOC_ID_RE.search(text)
    if m:
        return f"Document-ID pattern: {m.group()}"
    if _UNKNOWN_RE.search(text):
        return "Placeholder 'UNKNOWN' in rendered text"
    m = _SNAKE_3_RE.search(text)
    if m and _CYRILLIC_RE.search(text):
        return f"Snake-case identifier in Cyrillic context: {m.group()}"
    return None


def evaluate_leaked_identifiers(render_page: RenderPageV1) -> list[QARecordV1]:
    """Scan a render page for leaked technical identifiers.

    Returns one QARecordV1 per match.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.page_id if render_page.source_map else ""

    # Check page title
    reason = _check_text(render_page.page.title)
    if reason:
        records.append(_make_record(doc_id, page_id, "page.title", reason))

    # Check blocks
    for block in render_page.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        for child in block.children:
            if child.kind != "text":
                continue
            reason = _check_text(child.text)
            if reason:
                records.append(_make_record(doc_id, page_id, block.id, reason))
                break  # one record per block is enough

    return records


def _make_record(doc_id: str, page_id: str, entity_ref: str, reason: str) -> QARecordV1:
    return QARecordV1(
        qa_id=f"qa.{page_id}.leaked_id.{entity_ref}",
        layer=QALayer.RENDER,
        severity=Severity.ERROR,
        code="LEAKED_TECHNICAL_ID",
        document_id=doc_id,
        page_id=page_id,
        entity_ref=entity_ref,
        message=reason,
    )
