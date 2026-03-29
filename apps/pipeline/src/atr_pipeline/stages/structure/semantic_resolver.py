"""Semantic resolver — post-process blocks using region context."""

from __future__ import annotations

from dataclasses import dataclass, field

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.block_filter import (
    filter_figure_area_blocks,
    filter_heading_clusters,
)
from atr_schemas.common import Rect
from atr_schemas.enums import AnchorEdgeKind, BlockType, RegionKind
from atr_schemas.evidence_primitives_v1 import EvidenceTableCandidate
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.page_ir_v1 import (
    Block,
    CalloutBlock,
    CaptionBlock,
    FigureBlock,
    InlineNode,
    ParagraphBlock,
    TableBlock,
)
from atr_schemas.resolved_page_v1 import AnchorEdge, ResolvedBlock, ResolvedRegion


@dataclass
class SemanticResolution:
    """Output of the semantic resolver."""

    blocks: list[Block] = field(default_factory=list)
    anchor_edges: list[AnchorEdge] = field(default_factory=list)
    resolved_blocks: list[ResolvedBlock] = field(default_factory=list)
    block_classification_confidence: float = 1.0


def resolve_semantics(
    blocks: list[Block],
    regions: list[ResolvedRegion],
    evidence: PageEvidenceV1 | None,
    cfg: StructureConfig,
) -> SemanticResolution:
    """Post-process blocks using region context for richer IR and anchor edges."""
    if not blocks:
        return SemanticResolution()

    region_map = _assign_blocks_to_regions(blocks, regions)
    edges: list[AnchorEdge] = []

    blocks, caption_edges = _detect_captions(blocks, region_map, cfg)
    edges.extend(caption_edges)
    blocks = filter_figure_area_blocks(blocks, region_map, regions)
    blocks = filter_heading_clusters(blocks)
    blocks, callout_edges = _promote_callouts(blocks, region_map, regions)
    edges.extend(callout_edges)
    blocks, table_edges = _resolve_tables(blocks, evidence, cfg)
    edges.extend(table_edges)
    edges.extend(_build_region_edges(blocks, region_map))
    resolved = _build_resolved_blocks(blocks, region_map)
    enriched = sum(1 for b in blocks if not isinstance(b, ParagraphBlock))
    total = len(blocks)
    conf = enriched / total if total > 0 else 1.0
    conf = max(0.5, min(1.0, 0.7 + conf * 0.3))

    return SemanticResolution(
        blocks=blocks,
        anchor_edges=edges,
        resolved_blocks=resolved,
        block_classification_confidence=conf,
    )


def _block_center(block: Block) -> tuple[float, float] | None:
    bbox = getattr(block, "bbox", None)
    return ((bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2) if bbox else None


def _assign_blocks_to_regions(
    blocks: list[Block],
    regions: list[ResolvedRegion],
) -> dict[str, str]:
    """Map block_id -> region_id by center-point containment."""
    result: dict[str, str] = {}
    for block in blocks:
        center = _block_center(block)
        if center is None:
            continue
        cx, cy = center
        for region in regions:
            rb = region.bbox
            if rb.x0 <= cx <= rb.x1 and rb.y0 <= cy <= rb.y1:
                result[block.block_id] = region.region_id
                break
    return result


def _region_kind_map(regions: list[ResolvedRegion]) -> dict[str, RegionKind]:
    return {r.region_id: r.kind for r in regions}


def _detect_captions(
    blocks: list[Block],
    region_map: dict[str, str],
    cfg: StructureConfig,
) -> tuple[list[Block], list[AnchorEdge]]:
    """Detect paragraphs below figures and promote them to CaptionBlocks."""
    figures = [b for b in blocks if isinstance(b, FigureBlock) and b.bbox is not None]
    if not figures:
        return blocks, []

    edges: list[AnchorEdge] = []
    claimed_caption_ids: set[str] = set()
    caption_map: dict[str, str] = {}

    paragraphs = [b for b in blocks if isinstance(b, ParagraphBlock) and b.bbox is not None]
    for para in paragraphs:
        text = "".join(c.text for c in para.children if hasattr(c, "text"))
        if len(text) > cfg.caption_max_text_length:
            continue

        assert para.bbox is not None
        para_top = para.bbox.y0
        best_figure: FigureBlock | None = None
        best_gap = float("inf")

        for fig in figures:
            assert fig.bbox is not None
            fig_bottom = fig.bbox.y1
            gap = para_top - fig_bottom
            if 0 <= gap <= cfg.caption_proximity_pt and gap < best_gap:
                best_gap = gap
                best_figure = fig

        if best_figure is not None and best_figure.block_id not in claimed_caption_ids:
            caption_map[para.block_id] = best_figure.block_id
            claimed_caption_ids.add(best_figure.block_id)

    if not caption_map:
        return blocks, []

    new_blocks: list[Block] = []
    for block in blocks:
        if block.block_id in caption_map:
            fig_id = caption_map[block.block_id]
            assert isinstance(block, ParagraphBlock)
            caption = CaptionBlock(
                block_id=block.block_id,
                bbox=block.bbox,
                figure_block_id=fig_id,
                children=list(block.children),
            )
            new_blocks.append(caption)
            edges.append(
                AnchorEdge(
                    edge_kind=AnchorEdgeKind.CAPTION_TO_FIGURE,
                    source_id=block.block_id,
                    target_id=fig_id,
                )
            )
        else:
            new_blocks.append(block)

    return new_blocks, edges


def _promote_callouts(
    blocks: list[Block],
    region_map: dict[str, str],
    regions: list[ResolvedRegion],
) -> tuple[list[Block], list[AnchorEdge]]:
    """Wrap blocks in CALLOUT_AREA regions into CalloutBlocks."""
    kind_map = _region_kind_map(regions)
    callout_region_ids = {rid for rid, k in kind_map.items() if k == RegionKind.CALLOUT_AREA}
    if not callout_region_ids:
        return blocks, []

    edges: list[AnchorEdge] = []
    new_blocks: list[Block] = []
    # Group consecutive blocks in the same callout region
    i = 0
    while i < len(blocks):
        block = blocks[i]
        rid = region_map.get(block.block_id, "")
        if rid not in callout_region_ids:
            new_blocks.append(block)
            i += 1
            continue

        # Collect consecutive blocks in the same callout region
        group: list[Block] = [block]
        j = i + 1
        while j < len(blocks) and region_map.get(blocks[j].block_id, "") == rid:
            group.append(blocks[j])
            j += 1

        # Merge children from all blocks into a single CalloutBlock
        all_children: list[InlineNode] = []
        for b in group:
            children: list[InlineNode] = getattr(b, "children", [])
            all_children.extend(children)

        # Compute union bbox
        bboxes: list[Rect] = [b.bbox for b in group if getattr(b, "bbox", None) is not None]  # type: ignore[misc]
        callout_bbox = _union_bboxes(bboxes) if bboxes else None

        callout_id = f"{group[0].block_id}.callout"
        callout = CalloutBlock(
            block_id=callout_id,
            bbox=callout_bbox,
            region_id=rid,
            children=all_children,
        )
        new_blocks.append(callout)
        edges.append(
            AnchorEdge(
                edge_kind=AnchorEdgeKind.BLOCK_TO_CALLOUT,
                source_id=callout_id,
                target_id=rid,
            )
        )
        i = j

    return new_blocks, edges


def _union_bboxes(bboxes: list[Rect]) -> Rect:
    """Compute bounding union of multiple Rects."""
    first = bboxes[0]
    x0, y0, x1, y1 = first.x0, first.y0, first.x1, first.y1
    for b in bboxes[1:]:
        x0 = min(x0, b.x0)
        y0 = min(y0, b.y0)
        x1 = max(x1, b.x1)
        y1 = max(y1, b.y1)
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _bbox_overlap(a: Rect, b: Rect) -> float:
    """Compute intersection-over-minimum-area overlap between two rects."""
    ix0 = max(a.x0, b.x0)
    iy0 = max(a.y0, b.y0)
    ix1 = min(a.x1, b.x1)
    iy1 = min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    min_area = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
    return intersection / min_area if min_area > 0 else 0.0


def _resolve_tables(
    blocks: list[Block],
    evidence: PageEvidenceV1 | None,
    cfg: StructureConfig,
) -> tuple[list[Block], list[AnchorEdge]]:
    """Promote ParagraphBlocks with matching table evidence to TableBlocks."""
    if evidence is None:
        return blocks, []

    table_candidates = [e for e in evidence.entities if isinstance(e, EvidenceTableCandidate)]
    if not table_candidates:
        return blocks, []

    edges: list[AnchorEdge] = []
    new_blocks: list[Block] = []

    for block in blocks:
        # Only promote paragraph and list-item blocks — never figures, headings, etc.
        if not isinstance(block, (ParagraphBlock,)):
            new_blocks.append(block)
            continue
        bbox = block.bbox
        if bbox is None:
            new_blocks.append(block)
            continue

        # Find matching table candidate by bbox overlap
        best_candidate: EvidenceTableCandidate | None = None
        best_overlap = 0.0
        for tc in table_candidates:
            if tc.confidence < cfg.table_min_confidence:
                continue
            overlap = _bbox_overlap(bbox, tc.bbox)
            if overlap > 0.5 and overlap > best_overlap:
                best_overlap = overlap
                best_candidate = tc

        if best_candidate is not None:
            table = TableBlock(
                block_id=block.block_id,
                bbox=bbox,
                children=list(getattr(block, "children", [])),
            )
            new_blocks.append(table)
            edges.append(
                AnchorEdge(
                    edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
                    source_id=block.block_id,
                    target_id=best_candidate.evidence_id,
                )
            )
        else:
            new_blocks.append(block)

    return new_blocks, edges


def _build_region_edges(
    blocks: list[Block],
    region_map: dict[str, str],
) -> list[AnchorEdge]:
    """Emit BLOCK_TO_REGION edges for all blocks assigned to regions."""
    edges: list[AnchorEdge] = []
    for block in blocks:
        rid = region_map.get(block.block_id, "")
        if rid:
            edges.append(
                AnchorEdge(
                    edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
                    source_id=block.block_id,
                    target_id=rid,
                )
            )
    return edges


def _block_type_from_block(block: Block) -> BlockType:
    """Map a block instance to its BlockType enum value."""
    type_str = getattr(block, "type", "unknown")
    try:
        return BlockType(type_str)
    except ValueError:
        return BlockType.UNKNOWN


def _resolve_region_id(block: Block, region_map: dict[str, str]) -> str:
    """Get region_id for a block, checking block-level region_id for callouts."""
    # CalloutBlocks carry their region_id directly (set during promotion)
    if isinstance(block, CalloutBlock) and block.region_id:
        return block.region_id
    return region_map.get(block.block_id, "")


def reorder_blocks_by_regions(
    blocks: list[Block],
    regions: list[ResolvedRegion],
    main_flow_order: list[str],
) -> list[Block]:
    """Reorder blocks to match region-based spatial reading order."""
    if not main_flow_order or not blocks:
        return blocks

    region_map = _assign_blocks_to_regions(blocks, regions)
    region_pos = {rid: i for i, rid in enumerate(main_flow_order)}
    aside_pos = _map_aside_to_main(regions, region_pos)
    sentinel = len(main_flow_order)

    def _sort_key(item: tuple[int, Block]) -> tuple[int, float, int]:
        orig_idx, block = item
        rid = region_map.get(block.block_id)
        pos = region_pos.get(rid, aside_pos.get(rid, sentinel)) if rid is not None else sentinel
        bbox = getattr(block, "bbox", None)
        y0 = bbox.y0 if bbox is not None else 0.0
        return (pos, y0, orig_idx)

    indexed = list(enumerate(blocks))
    indexed.sort(key=_sort_key)
    return [block for _, block in indexed]


def _map_aside_to_main(regions: list[ResolvedRegion], region_pos: dict[str, int]) -> dict[str, int]:
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


def _build_resolved_blocks(
    blocks: list[Block],
    region_map: dict[str, str],
) -> list[ResolvedBlock]:
    """Emit ResolvedBlock entries for ResolvedPageV1."""
    return [
        ResolvedBlock(
            block_id=block.block_id,
            block_type=_block_type_from_block(block),
            region_id=_resolve_region_id(block, region_map),
        )
        for block in blocks
    ]
