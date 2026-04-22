"""Block reordering — translate region-level reading order into block order.

Separated from ``semantic_resolver`` in S5U-700 so the column-aware fallback
(used when the region layer collapses a two-column page into one wide region)
could land without pushing ``semantic_resolver.py`` past the 400-line ceiling.

The public entry point is :func:`reorder_blocks_by_regions`, which preserves
its original signature.
"""

from __future__ import annotations

from atr_schemas.enums import RegionKind
from atr_schemas.page_ir_v1 import Block
from atr_schemas.resolved_page_v1 import ResolvedRegion

# A region is considered "wide enough to hide columns" when its width spans
# this fraction of the page. Combined with >= _COLUMN_FALLBACK_MIN_BLOCKS
# blocks assigned to it, the column-aware fallback activates.
_WIDE_REGION_WIDTH_FRACTION = 0.75
_COLUMN_FALLBACK_MIN_BLOCKS = 4


def reorder_blocks_by_regions(
    blocks: list[Block],
    regions: list[ResolvedRegion],
    main_flow_order: list[str],
) -> list[Block]:
    """Reorder blocks to match region-based spatial reading order.

    S5U-700: when all blocks in a main-flow region pile into a single wide
    region (typical symptom: a page-spanning FULL_WIDTH vector-background
    region, or gutter-detection failure inside ``region_graph``), fall back
    to column-aware ordering — detect the gutter x-coordinate from the
    block x-distribution and emit left-column (centre x < gutter) before
    right-column. A single-column page degenerates back to y0-only sort
    with no behaviour change.
    """
    # Import is local to avoid a cycle with semantic_resolver; both modules
    # need the region-map primitive.
    from atr_pipeline.stages.structure.semantic_resolver import (
        _assign_blocks_to_regions,
    )

    if not main_flow_order or not blocks:
        return blocks

    region_map = _assign_blocks_to_regions(blocks, regions)
    region_pos = {rid: i for i, rid in enumerate(main_flow_order)}
    aside_pos = _map_aside_to_main(regions, region_pos)
    sentinel = len(main_flow_order)
    region_by_id = {r.region_id: r for r in regions}

    # Compute per-region column splits for wide regions only. Keyed by
    # region_id; value is a gutter x-coordinate or None (no split needed).
    gutter_by_region = _compute_column_gutters(
        blocks, region_map, region_by_id
    )

    def _block_x_center(block: Block) -> float:
        bbox = getattr(block, "bbox", None)
        return (bbox.x0 + bbox.x1) / 2 if bbox is not None else 0.0

    def _sort_key(item: tuple[int, Block]) -> tuple[int, int, float, int]:
        orig_idx, block = item
        rid = region_map.get(block.block_id)
        if rid is None:
            return (sentinel, 0, 0.0, orig_idx)
        pos = region_pos.get(rid, aside_pos.get(rid, sentinel))
        gutter = gutter_by_region.get(rid)
        if gutter is not None:
            column = 0 if _block_x_center(block) < gutter else 1
        else:
            column = 0
        bbox = getattr(block, "bbox", None)
        y0 = bbox.y0 if bbox is not None else 0.0
        return (pos, column, y0, orig_idx)

    indexed = list(enumerate(blocks))
    indexed.sort(key=_sort_key)
    return [block for _, block in indexed]


def _map_aside_to_main(
    regions: list[ResolvedRegion], region_pos: dict[str, int]
) -> dict[str, int]:
    """Map non-main-flow region IDs to nearest main-flow region position."""
    main = [r for r in regions if r.region_id in region_pos]
    if not main:
        return {}
    result: dict[str, int] = {}
    for r in regions:
        if r.region_id in region_pos:
            continue
        cy = (r.bbox.y0 + r.bbox.y1) / 2
        best = min(main, key=lambda m: abs(cy - (m.bbox.y0 + m.bbox.y1) / 2))
        result[r.region_id] = region_pos[best.region_id]
    return result


def _compute_column_gutters(
    blocks: list[Block],
    region_map: dict[str, str],
    region_by_id: dict[str, ResolvedRegion],
) -> dict[str, float]:
    """For each wide region that holds enough blocks, detect a column gutter.

    Returns a mapping of region_id -> gutter_x. Regions that are narrow,
    hold too few blocks, or whose block x-distribution shows no clear gap
    do not appear in the result (meaning: fall back to y0-only ordering).
    """
    # Group blocks by assigned region for quick inspection.
    by_region: dict[str, list[Block]] = {}
    for block in blocks:
        rid = region_map.get(block.block_id)
        if rid is None:
            continue
        by_region.setdefault(rid, []).append(block)

    result: dict[str, float] = {}
    for rid, region_blocks in by_region.items():
        region = region_by_id.get(rid)
        if region is None:
            continue
        if region.kind not in _column_eligible_kinds():
            continue
        region_width = region.bbox.x1 - region.bbox.x0
        if region_width <= 0:
            continue
        # Narrow regions stay single-column — y0 order is already correct.
        if region.kind == RegionKind.FULL_WIDTH:
            # Full-width decorative regions are always wide enough by
            # definition, but we still require a block-count floor to
            # avoid splitting a region holding a single stray block.
            pass
        else:
            page_like_width = region_width
            # Use the region's own width as the reference — a 75%-of-itself
            # check is meaningless. Instead, gate on an absolute minimum
            # width in PDF points where two A4 columns plausibly fit.
            if page_like_width < 400.0:
                continue
        if len(region_blocks) < _COLUMN_FALLBACK_MIN_BLOCKS:
            continue

        gutter = _detect_block_gutter(region_blocks, region)
        if gutter is not None:
            result[rid] = gutter
    return result


def _column_eligible_kinds() -> frozenset[RegionKind]:
    """Region kinds where a column-aware fallback is meaningful."""
    return frozenset(
        {
            RegionKind.BODY,
            RegionKind.FULL_WIDTH,
            RegionKind.TABLE_AREA,
            RegionKind.UNKNOWN,
        }
    )


def _detect_block_gutter(
    blocks: list[Block], region: ResolvedRegion
) -> float | None:
    """Find the x-coordinate of a gutter between two block columns.

    Uses the blocks' own x-centres rather than the evidence spans that
    feed ``region_graph`` — because this is a fallback that activates
    *after* region segmentation has already failed to split columns.

    Returns ``None`` if the blocks show a single-column distribution.
    """
    centres = sorted(
        ((b.bbox.x0 + b.bbox.x1) / 2 for b in blocks if b.bbox is not None)
    )
    if len(centres) < 2:
        return None

    region_width = region.bbox.x1 - region.bbox.x0
    # Only look for a gap in the middle third of the region — a valid page
    # gutter cannot be at the far left or right.
    mid_low = region.bbox.x0 + region_width * 0.3
    mid_high = region.bbox.x0 + region_width * 0.7

    # Largest gap between consecutive centres inside the middle band.
    best_gap = 0.0
    best_mid = -1.0
    for i in range(1, len(centres)):
        prev_c = centres[i - 1]
        cur_c = centres[i]
        mid = (prev_c + cur_c) / 2
        if mid < mid_low or mid > mid_high:
            continue
        gap = cur_c - prev_c
        if gap > best_gap:
            best_gap = gap
            best_mid = mid

    # Require a reasonably wide gap relative to the region. This trips on
    # classic two-column pages where the inter-column gap is tens of
    # points while within-column block centres cluster tightly.
    if best_mid < 0 or best_gap < region_width * 0.1:
        return None

    # Require both sides to have at least one block — otherwise one stray
    # far-right block could fake a split.
    left = sum(1 for c in centres if c < best_mid)
    right = sum(1 for c in centres if c >= best_mid)
    if left < 2 or right < 2:
        return None

    return best_mid
