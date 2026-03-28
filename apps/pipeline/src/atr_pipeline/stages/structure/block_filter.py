"""Block-level filters — remove diagram noise before semantic enrichment."""

from __future__ import annotations

from atr_schemas.enums import RegionKind
from atr_schemas.native_page_v1 import ImageBlockEvidence, SpanEvidence
from atr_schemas.page_ir_v1 import Block, HeadingBlock, ParagraphBlock
from atr_schemas.resolved_page_v1 import ResolvedRegion

# Minimum run length of consecutive short headings to treat as diagram noise.
_HEADING_CLUSTER_MIN_RUN = 3
# Maximum text length for a heading to count toward a diagram-label cluster.
_HEADING_CLUSTER_MAX_TEXT = 5


def filter_figure_area_blocks(
    blocks: list[Block],
    region_map: dict[str, str],
    regions: list[ResolvedRegion],
) -> list[Block]:
    """Remove paragraph/heading blocks whose center falls in a FIGURE_AREA region.

    Text that lands inside an image-dominated region is almost always a diagram
    label, form-field text, or photographed-card text — not real prose.
    CaptionBlocks and FigureBlocks are kept unconditionally.
    """
    kind_map = {r.region_id: r.kind for r in regions}
    figure_region_ids = {rid for rid, k in kind_map.items() if k == RegionKind.FIGURE_AREA}
    if not figure_region_ids:
        return blocks
    return [
        b
        for b in blocks
        if not (
            isinstance(b, (ParagraphBlock, HeadingBlock))
            and region_map.get(b.block_id, "") in figure_region_ids
        )
    ]


def figure_overlap_span_ids(
    spans: list[SpanEvidence],
    images: list[ImageBlockEvidence],
    max_text_len: int = 5,
    tolerance: float = 2.0,
) -> set[str]:
    """Return span IDs for short text spans contained within significant images.

    Diagram callout numbers and labels sit on top of raster figures.  Filtering
    them prevents "1", "2", "3" etc. from becoming prose blocks.
    """
    if not images:
        return set()
    result: set[str] = set()
    for span in spans:
        if len(span.text.strip()) > max_text_len:
            continue
        for img in images:
            if (
                span.bbox.x0 >= img.bbox.x0 - tolerance
                and span.bbox.x1 <= img.bbox.x1 + tolerance
                and span.bbox.y0 >= img.bbox.y0 - tolerance
                and span.bbox.y1 <= img.bbox.y1 + tolerance
            ):
                result.add(span.span_id)
                break
    return result


def filter_heading_clusters(
    blocks: list[Block],
) -> list[Block]:
    """Remove runs of consecutive short headings that are likely diagram labels.

    Three or more adjacent headings whose text is at most 5 characters each are
    almost certainly callout numbers or axis labels on a diagram, not real
    section headings.
    """
    if len(blocks) < _HEADING_CLUSTER_MIN_RUN:
        return blocks

    drop_ids: set[str] = set()
    run_start = 0
    while run_start < len(blocks):
        b = blocks[run_start]
        if not _is_short_heading(b):
            run_start += 1
            continue
        run_end = run_start + 1
        while run_end < len(blocks) and _is_short_heading(blocks[run_end]):
            run_end += 1
        if run_end - run_start >= _HEADING_CLUSTER_MIN_RUN:
            for i in range(run_start, run_end):
                drop_ids.add(blocks[i].block_id)
        run_start = run_end

    if not drop_ids:
        return blocks
    return [b for b in blocks if b.block_id not in drop_ids]


def _is_short_heading(block: Block) -> bool:
    """Check if a block is a heading with very short text."""
    if not isinstance(block, HeadingBlock):
        return False
    text = " ".join(c.text for c in block.children if hasattr(c, "text"))
    return len(text.strip()) <= _HEADING_CLUSTER_MAX_TEXT
