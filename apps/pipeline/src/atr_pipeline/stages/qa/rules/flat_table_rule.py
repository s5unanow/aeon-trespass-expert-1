"""QA rule: detect flat TableBlocks that lack row/cell structure.

S5U-704 — after structure recovery, a ``RenderTableBlock`` whose
``children`` list is a long run of flat ``RenderTextInline`` entries
with no ``RenderTableRowBlock`` grandchildren almost always means the
structure layer (or the ``semantic_resolver._resolve_tables`` promotion
path) emitted a table without the cell geometry that the reader needs
to render as a proper grid. Such tables show up in the reader as a
pre-wrap wall of text.

This rule flags the condition as ERROR so a release cannot silently
ship a chart with the row/cell semantics stripped out. The threshold
(>=20 inline children) is tuned above the size of typical split-header
TableBlocks (which carry 2-4 inlines) but below the chart-body sizes
observed in the S5U-704 evidence (p0054.b002 = 177 inlines).
"""

from __future__ import annotations

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.render_page_v1 import (
    RenderPageV1,
    RenderTableBlock,
    RenderTableRowBlock,
)

# Minimum number of flat inline children that triggers the rule. Below
# this threshold a table is assumed to be a legitimate small structure
# (split header, narrow callout, etc.) even if it lacks row nesting.
_MIN_FLAT_CHILDREN = 20


def _is_structured(block: RenderTableBlock) -> bool:
    """A table is structured iff at least one child is a ``RenderTableRowBlock``."""
    return any(isinstance(c, RenderTableRowBlock) for c in block.children)


def evaluate_flat_table(render_page: RenderPageV1) -> list[QARecordV1]:
    """Flag ``RenderTableBlock``s that carry no row/cell nesting.

    Only tables with at least ``_MIN_FLAT_CHILDREN`` flat children are
    reported; smaller tables are too likely to be legitimate single-row
    or split-header structures for the signal-to-noise trade-off to be
    worth the noise.
    """
    records: list[QARecordV1] = []
    page_id = render_page.page.id
    doc_id = render_page.source_map.page_id if render_page.source_map else ""

    for block in render_page.blocks:
        if not isinstance(block, RenderTableBlock):
            continue
        if _is_structured(block):
            continue
        if len(block.children) < _MIN_FLAT_CHILDREN:
            continue
        records.append(
            QARecordV1(
                qa_id=f"qa.{page_id}.flat_table.{block.id}",
                layer=QALayer.STRUCTURE,
                severity=Severity.ERROR,
                code="FLAT_TABLE_NO_ROWS",
                document_id=doc_id,
                page_id=page_id,
                entity_ref=block.id,
                message=(
                    f"TableBlock has {len(block.children)} flat inline "
                    "children and no table_row/table_cell structure. "
                    "The reader cannot render row/column semantics; "
                    "likely a chart body was flattened during structure "
                    "recovery (S5U-704)."
                ),
            )
        )

    return records
