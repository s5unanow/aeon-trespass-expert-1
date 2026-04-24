"""QA rule: detect decorative icon leakage in rendered text."""

from __future__ import annotations

import re

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import AutoFix, QARecordV1
from atr_schemas.render_page_v1 import RenderDividerBlock, RenderPageV1

# Raw asset tokens: two uppercase letters followed by four digits
ASSET_TOKEN_RE = re.compile(r"\b[A-Z]{2}\d{4}\b")

# Stage-internal codes: T##T## pattern
STAGE_CODE_RE = re.compile(r"\bT\d{2}T\d{2}\b")

# Isolated placeholder chars: lone dot or alpha surrounded by spaces
PLACEHOLDER_RE = re.compile(r"(?:^|\s)[.\u03B1](?:\s|$)")

# Unicode range for GreenleafBanners-style private-use / decorative glyphs
PRIVATE_USE_RE = re.compile(r"[\uE000-\uF8FF]")

# S5U-701 -- descriptive placeholder prose left behind when the extractor
# dropped actual icons.  Shape observed in the Apr-22 EN bundle:
#
#     p0009.b026 -- "Potential symbol Power symbol ??? symbol"
#
# The literal phrase "<concept> symbol" is never legitimate body text in
# Aeon Trespass rules (game text refers to "the Potential", not "the
# Potential symbol").  Matching on the known concept names plus the
# question-mark fallback keeps the false-positive rate near zero while
# catching the exact failure mode.
_PLACEHOLDER_CONCEPTS = (
    r"Potential|Power|Progress|Fate|Will|Argo[- ]?Fate"
    r"|Kratos|Danger|Break|Hope|Doom"
)
# Two alternations because the "???" prefix can't be preceded by \b (? isn't a
# word character).  The named-concept prefix keeps \b so we don't match
# substrings like "superPower symbol".
PLACEHOLDER_PROSE_RE = re.compile(
    rf"(?:\b(?:{_PLACEHOLDER_CONCEPTS})|\?\?\?)\s+symbol\b",
    re.IGNORECASE,
)

DECORATIVE_PATTERNS: list[re.Pattern[str]] = [
    ASSET_TOKEN_RE,
    STAGE_CODE_RE,
    PRIVATE_USE_RE,
    PLACEHOLDER_RE,
]


def _check_text(text: str) -> str | None:
    """Return a reason string if *text* contains leaked icon content."""
    m = ASSET_TOKEN_RE.search(text)
    if m:
        return f"Raw asset token: {m.group()}"
    m = STAGE_CODE_RE.search(text)
    if m:
        return f"Stage-internal code: {m.group()}"
    m = PRIVATE_USE_RE.search(text)
    if m:
        return f"Private-use glyph: U+{ord(m.group()):04X}"
    if PLACEHOLDER_RE.search(text):
        return "Isolated placeholder character (likely missing icon)"
    return None


def _check_placeholder_prose(text: str) -> str | None:
    """Return a reason string if *text* contains descriptive placeholder prose.

    S5U-701 -- distinct from ``_check_text`` because severity and code
    differ (ERROR + PLACEHOLDER_PROSE_LEAKED vs WARNING +
    DECORATIVE_ICON_LEAKED).  Kept separate so reviewer triage and
    metrics dashboards can distinguish the two failure classes.
    """
    m = PLACEHOLDER_PROSE_RE.search(text)
    if m:
        return f"Descriptive placeholder prose: '{m.group()}'"
    return None


def evaluate_decorative_icons(render_page: RenderPageV1) -> list[QARecordV1]:
    """Scan a render page for leaked decorative icon content.

    Returns at most one ``DECORATIVE_ICON_LEAKED`` (WARNING) and one
    ``PLACEHOLDER_PROSE_LEAKED`` (ERROR) record per block.  When both
    patterns match the same block, both records are emitted so reviewer
    and metrics flows see them distinctly.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.document_id if render_page.source_map else ""

    for block in render_page.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        decorative_recorded = False
        placeholder_recorded = False
        for child in block.children:
            if child.kind != "text":
                continue
            if not decorative_recorded:
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
                            auto_fix=AutoFix(available=True, fixer="remove_decorative"),
                        )
                    )
                    decorative_recorded = True
            if not placeholder_recorded:
                prose_reason = _check_placeholder_prose(child.text)
                if prose_reason:
                    records.append(
                        QARecordV1(
                            qa_id=f"qa.{page_id}.placeholder_prose.{block.id}",
                            layer=QALayer.RENDER,
                            severity=Severity.ERROR,
                            code="PLACEHOLDER_PROSE_LEAKED",
                            document_id=doc_id,
                            page_id=page_id,
                            entity_ref=block.id,
                            message=prose_reason,
                        )
                    )
                    placeholder_recorded = True
            if decorative_recorded and placeholder_recorded:
                break

    return records
