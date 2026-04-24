"""Table row / cell assembly from spans.

Extracted from ``real_block_builder`` in S5U-710. No behavior changes.

Provides the primitives the main structure orchestrator uses to:

* split a single y-baseline into table cells by horizontal x-gap
  (``_split_spans_by_x_gap`` — S5U-698 table/heading split, S5U-704
  structured row/cell emission),
* assemble a ``TableRowBlock`` from ordered cell groups
  (``_build_table_row`` — S5U-704),
* determine whether a line belongs to a config-driven table region
  (``_line_in_table_region``).
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.span_classify import (
    _bbox_from_spans,
    _spans_to_text_inline,
)
from atr_schemas.common import Rect
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.page_ir_v1 import TableCellBlock, TableRowBlock


def _split_spans_by_x_gap(
    spans: list[SpanEvidence],
    gap_threshold_pt: float,
) -> list[list[SpanEvidence]]:
    """Split spans on the same y-baseline into cell groups by horizontal gap.

    S5U-698 — a heading-classified line composed of multiple spans with
    gaps wider than ``gap_threshold_pt`` is almost certainly a multi-column
    table-header row rather than a single heading. Returning a list of
    length > 1 is the signal that the structure layer must refuse to emit
    one joined heading.
    """
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: s.bbox.x0)
    groups: list[list[SpanEvidence]] = [[ordered[0]]]
    for span in ordered[1:]:
        prev = groups[-1][-1]
        gap = span.bbox.x0 - prev.bbox.x1
        if gap > gap_threshold_pt:
            groups.append([span])
        else:
            groups[-1].append(span)
    return groups


def _build_table_row(
    cell_groups: list[list[SpanEvidence]],
    cfg: StructureConfig,
    parent_block_id: str,
    row_index: int,
    *,
    header: bool = False,
) -> TableRowBlock | None:
    """Assemble a ``TableRowBlock`` from ordered cell-groups of spans.

    S5U-704 — each ``cell_groups`` entry becomes one ``TableCellBlock``
    with its own inline run (via ``_spans_to_text_inline``). Empty groups
    are skipped; the row is refused (``None``) if no cell produces any
    non-empty inline.  Block ids are suffixed with ``.rN`` and ``.rN.cM``
    relative to the parent table block id so they are stable and unique
    within the page.
    """
    cells: list[TableCellBlock] = []
    for ci, group in enumerate(cell_groups):
        inlines = _spans_to_text_inline(group, cfg)
        if not inlines:
            continue
        cells.append(
            TableCellBlock(
                block_id=f"{parent_block_id}.r{row_index}.c{ci}",
                bbox=_bbox_from_spans(group),
                header=header,
                children=list(inlines),
            )
        )
    if not cells:
        return None
    return TableRowBlock(
        block_id=f"{parent_block_id}.r{row_index}",
        bbox=_bbox_from_spans([s for grp in cell_groups for s in grp]),
        header=header,
        cells=cells,
    )


def _line_in_table_region(
    spans: list[SpanEvidence],
    table_regions: list[Rect],
    tolerance: float = 5.0,
) -> int:
    """Return index of the table region containing the majority of spans, or -1."""
    for idx, region in enumerate(table_regions):
        count = sum(
            1
            for s in spans
            if (
                region.x0 - tolerance <= (s.bbox.x0 + s.bbox.x1) / 2 <= region.x1 + tolerance
                and region.y0 - tolerance <= (s.bbox.y0 + s.bbox.y1) / 2 <= region.y1 + tolerance
            )
        )
        if count > len(spans) / 2:
            return idx
    return -1
