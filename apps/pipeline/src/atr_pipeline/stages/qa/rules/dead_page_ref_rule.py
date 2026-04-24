"""QA rule: detect dead PDF page references in rendered text."""

from __future__ import annotations

import re
from collections.abc import Sequence

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import (
    RenderDividerBlock,
    RenderInlineNode,
    RenderPageV1,
    RenderTableBlock,
    RenderTableRowBlock,
)

# Russian: "стр. 16", "стр.16", "стр 16"
_STR_RE = re.compile(r"\u0441\u0442\u0440\.?\s*\d+")

# English: "p. 16", "p.16"
_P_DOT_RE = re.compile(r"\bp\.\s*\d+", re.IGNORECASE)

# English: "page 16"
_PAGE_RE = re.compile(r"\bpage\s+\d+", re.IGNORECASE)

# Pull the trailing digit run out of a raw match ("p. 60." -> "60").
_DIGITS_RE = re.compile(r"\d+")


def _iter_page_refs(text: str) -> list[str]:
    """Return every page-reference match found in *text* in source order."""
    hits: list[tuple[int, str]] = []
    for pattern in (_STR_RE, _P_DOT_RE, _PAGE_RE):
        for m in pattern.finditer(text):
            hits.append((m.start(), m.group()))
    hits.sort(key=lambda h: h[0])
    return [h[1] for h in hits]


def _extract_target_page_number(ref: str) -> int | None:
    """Parse the trailing digit run of a matched reference.

    Returns the page number as an int, or ``None`` when the reference has no
    digit run (guarded defensively so a pattern tweak upstream doesn't
    produce a crash here).
    """
    m = _DIGITS_RE.search(ref)
    if not m:
        return None
    try:
        return int(m.group())
    except ValueError:  # pragma: no cover - _DIGITS_RE guarantees digits
        return None


def evaluate_dead_page_refs(
    render_page: RenderPageV1,
    known_page_numbers: frozenset[int] | None = None,
) -> list[QARecordV1]:
    """Scan a render page for dead PDF page references.

    Returns one QARecordV1 per affected block.

    When ``known_page_numbers`` is supplied the rule consults it as the
    manifest of published page numbers and suppresses references whose
    target is in the set — those are false positives (S5U-701: p0008
    cited "p. 60" which IS published).

    When ``known_page_numbers`` is ``None`` the rule preserves its legacy
    behavior of reporting every matched page reference.  This is the
    fallback for ad-hoc invocations that cannot enumerate the page set
    and for isolated unit tests of a single render page.  An explicitly
    empty frozenset is distinct: it means "zero pages are known", so every
    ref is treated as dead.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.document_id if render_page.source_map else ""

    for block in render_page.blocks:
        if isinstance(block, RenderDividerBlock):
            continue
        # S5U-704 — ``RenderTableBlock.children`` may contain nested
        # ``RenderTableRowBlock`` entries whose cells hold the real
        # inlines. Flatten here so the scan still sees every text node.
        children: Sequence[RenderInlineNode]
        if isinstance(block, RenderTableBlock):
            children = _flatten_table_inlines(block)
        else:
            children = block.children
        dead_ref = _first_dead_ref_in_block(children, known_page_numbers)
        if dead_ref is None:
            continue
        records.append(
            QARecordV1(
                qa_id=f"qa.{page_id}.dead_page_ref.{block.id}",
                layer=QALayer.RENDER,
                severity=Severity.WARNING,
                code="DEAD_PAGE_REF",
                document_id=doc_id,
                page_id=page_id,
                entity_ref=block.id,
                message=f"Dead page reference: '{dead_ref}'",
            )
        )

    return records


def _flatten_table_inlines(block: RenderTableBlock) -> list[RenderInlineNode]:
    """S5U-704 — flatten a RenderTableBlock's nested rows/cells so the
    dead-page-ref scanner can see every inline text node regardless of
    whether the table is structured or still flat."""
    out: list[RenderInlineNode] = []
    for child in block.children:
        if isinstance(child, RenderTableRowBlock):
            for cell in child.cells:
                out.extend(cell.children)
        else:
            out.append(child)
    return out


def _first_dead_ref_in_block(
    children: Sequence[RenderInlineNode],
    known_page_numbers: frozenset[int] | None,
) -> str | None:
    """Return the first dead page reference across a block's children.

    Walking children in source order means "dead" vs. "published" refs are
    tracked independently per block: a block that cites both "p. 60"
    (published) and "p. 999" (missing) emits once on the 999 ref, while
    a block that cites only published refs emits nothing.
    """
    for child in children:
        if child.kind != "text":
            continue
        for ref in _iter_page_refs(child.text):
            if known_page_numbers is None:
                return ref
            target = _extract_target_page_number(ref)
            if target is None or target not in known_page_numbers:
                return ref
    return None
