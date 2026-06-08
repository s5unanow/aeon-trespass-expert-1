"""S5U-1007 — a callout region containing a table must not crash structure.

``_promote_callouts`` merges the children of every block grouped into a
``CALLOUT_AREA`` region into a single inline-only ``CalloutBlock``. A
``TableBlock`` caught in such a region carries ``TableRowBlock`` children
(structured rows, S5U-704), which the inline-only ``CalloutBlock.children``
union rejects — the first full 83-page run aborted at the structure stage with
``union_tag_invalid`` on a callout-with-table page. The fix flattens any table
to inlines via ``iter_table_inlines`` (a callout renders as a flat inline run;
``RenderCalloutBlock`` is inline-only), preserving all cell content.

Lives in its own file rather than growing the grandfathered
``test_semantic_resolver.py`` (KNOWN_VIOLATORS, >400 lines).
"""

from __future__ import annotations

from atr_pipeline.stages.structure.semantic_resolver import _promote_callouts
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.page_ir_v1 import (
    CalloutBlock,
    IconInline,
    TableBlock,
    TableCellBlock,
    TableRowBlock,
    TextInline,
)
from atr_schemas.resolved_page_v1 import ResolvedRegion

_DIMS = PageDimensions(width=612.0, height=792.0)


def _rect(x0: float, y0: float, x1: float, y1: float) -> Rect:
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _norm(r: Rect) -> NormRect:
    return NormRect(
        x0=max(0.0, min(1.0, r.x0 / _DIMS.width)),
        y0=max(0.0, min(1.0, r.y0 / _DIMS.height)),
        x1=max(0.0, min(1.0, r.x1 / _DIMS.width)),
        y1=max(0.0, min(1.0, r.y1 / _DIMS.height)),
    )


def _region(
    rid: str, kind: RegionKind, x0: float, y0: float, x1: float, y1: float
) -> ResolvedRegion:
    bbox = _rect(x0, y0, x1, y1)
    return ResolvedRegion(region_id=rid, kind=kind, bbox=bbox, norm_bbox=_norm(bbox))


def _table_with_rows() -> TableBlock:
    return TableBlock(
        block_id="t1",
        bbox=_rect(50, 100, 200, 140),
        children=[
            TableRowBlock(
                block_id="t1.r1",
                cells=[
                    TableCellBlock(block_id="t1.r1.c1", children=[TextInline(text="Name")]),
                    TableCellBlock(
                        block_id="t1.r1.c2",
                        children=[
                            TextInline(text="Danger "),
                            IconInline(symbol_id="sym.danger"),
                        ],
                    ),
                ],
            ),
            TableRowBlock(
                block_id="t1.r2",
                cells=[
                    TableCellBlock(block_id="t1.r2.c1", children=[TextInline(text="Alice")]),
                    TableCellBlock(block_id="t1.r2.c2", children=[TextInline(text="42")]),
                ],
            ),
        ],
    )


def test_callout_region_with_table_flattens_rows() -> None:
    """A TableBlock in a callout region flattens to inlines (no crash)."""
    table = _table_with_rows()
    regions = [_region("r001", RegionKind.CALLOUT_AREA, 40, 90, 210, 150)]

    blocks, _edges = _promote_callouts([table], {"t1": "r001"}, regions)

    callouts = [b for b in blocks if isinstance(b, CalloutBlock)]
    assert len(callouts) == 1
    # No TableRowBlock leaked into the inline-only callout children.
    assert all(not isinstance(c, TableRowBlock) for c in callouts[0].children)
    # All cell text is preserved in reading order; no dropped segments.
    texts = [c.text for c in callouts[0].children if isinstance(c, TextInline)]
    assert texts == ["Name", "Danger ", "Alice", "42"]
    # The icon cell content survives the flatten too.
    assert any(isinstance(c, IconInline) for c in callouts[0].children)


def test_callout_region_with_plain_blocks_unchanged() -> None:
    """Non-table callout content still flattens its inline children directly."""
    from atr_schemas.page_ir_v1 import ParagraphBlock

    para = ParagraphBlock(
        block_id="b1",
        bbox=_rect(50, 100, 200, 120),
        children=[TextInline(text="Sidebar note")],
    )
    regions = [_region("r001", RegionKind.CALLOUT_AREA, 40, 90, 210, 130)]

    blocks, _edges = _promote_callouts([para], {"b1": "r001"}, regions)

    callouts = [b for b in blocks if isinstance(b, CalloutBlock)]
    assert len(callouts) == 1
    texts = [c.text for c in callouts[0].children if isinstance(c, TextInline)]
    assert texts == ["Sidebar note"]
