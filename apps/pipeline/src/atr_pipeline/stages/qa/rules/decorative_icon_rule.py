"""QA rule: detect decorative icon leakage in rendered text."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

# Raw asset tokens: two uppercase letters followed by four digits
_ASSET_TOKEN_RE = re.compile(r"\b[A-Z]{2}\d{4}\b")

# Stage-internal codes: T##T## pattern
_STAGE_CODE_RE = re.compile(r"\bT\d{2}T\d{2}\b")

# Isolated placeholder chars: lone dot or alpha surrounded by spaces
_PLACEHOLDER_RE = re.compile(r"(?:^|\s)[.\u03B1](?:\s|$)")

# Unicode range for GreenleafBanners-style private-use / decorative glyphs
_PRIVATE_USE_RE = re.compile(r"[\uE000-\uF8FF]")


def _check_text(text: str) -> str | None:
    """Return a reason string if *text* contains leaked icon content."""
    m = _ASSET_TOKEN_RE.search(text)
    if m:
        return f"Raw asset token: {m.group()}"
    m = _STAGE_CODE_RE.search(text)
    if m:
        return f"Stage-internal code: {m.group()}"
    m = _PRIVATE_USE_RE.search(text)
    if m:
        return f"Private-use glyph: U+{ord(m.group()):04X}"
    if _PLACEHOLDER_RE.search(text):
        return "Isolated placeholder character (likely missing icon)"
    return None


def evaluate_decorative_icons(render_page: RenderPageV1) -> list[QARecordV1]:
    """Scan a render page for leaked decorative icon content.

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
                        qa_id=f"qa.{page_id}.decorative_icon.{block.id}",
                        layer=QALayer.RENDER,
                        severity=Severity.WARNING,
                        code="DECORATIVE_ICON_LEAKED",
                        document_id=doc_id,
                        page_id=page_id,
                        entity_ref=block.id,
                        message=reason,
                    )
                )
                break  # one record per block

    return records
