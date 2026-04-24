"""Paragraph→TableBlock promotion via bbox-overlap with table evidence.

Extracted from ``semantic_resolver`` in S5U-733. The previous implementation
copied the paragraph's flat inline children verbatim when promoting, which
preserved the flat-inline failure mode (live ``p0054.b002`` showed 177 flat
inlines / 0 rows). This module re-infers row/cell structure from native
spans inside the table candidate's bbox; when that fails it refuses
promotion so the block stays a ``ParagraphBlock``.
"""

from __future__ import annotations

from atr_pipeline.config.models import StructureConfig
from atr_pipeline.stages.structure.table_assembly import build_table_rows_from_spans
from atr_schemas.common import Rect
from atr_schemas.enums import AnchorEdgeKind
from atr_schemas.evidence_primitives_v1 import EvidenceTableCandidate
from atr_schemas.native_page_v1 import NativePageV1
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.page_ir_v1 import Block, ParagraphBlock, TableBlock
from atr_schemas.resolved_page_v1 import AnchorEdge


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
    native: NativePageV1 | None = None,
) -> tuple[list[Block], list[AnchorEdge]]:
    """Promote ParagraphBlocks with matching table evidence to TableBlocks.

    S5U-733 — when ``native`` is provided, re-derive row/cell structure
    from native spans inside the table candidate's bbox via
    ``build_table_rows_from_spans`` (Option 1). When the re-inference
    produces at least one row, the promoted TableBlock carries
    ``TableRowBlock`` children (same contract as
    ``real_block_builder.flush_table``).

    When ``native`` is unavailable OR the span-based re-inference yields
    zero rows (no spans inside the candidate bbox, or no non-empty cells),
    the promotion is refused and the block is left as a
    ``ParagraphBlock`` (Option 2 fallback). A TableBlock without
    structured rows would otherwise preserve the flat-inline failure mode
    the live p0054.b002 artifact exhibits and the ``FLAT_TABLE_NO_ROWS``
    QA rule guards.
    """
    if evidence is None:
        return blocks, []

    table_candidates = [e for e in evidence.entities if isinstance(e, EvidenceTableCandidate)]
    if not table_candidates:
        return blocks, []

    edges: list[AnchorEdge] = []
    new_blocks: list[Block] = []

    for block in blocks:
        # Only promote paragraph and list-item blocks — never figures, headings, etc.
        if not isinstance(block, ParagraphBlock):
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

        if best_candidate is None:
            new_blocks.append(block)
            continue

        row_blocks = (
            build_table_rows_from_spans(
                native.spans,
                best_candidate.bbox,
                cfg,
                block.block_id,
            )
            if native is not None
            else []
        )
        if not row_blocks:
            # Option 2 fallback — refuse promotion when we can't prove
            # multi-row structure. Prevents emitting a flat-inline
            # TableBlock that would trip the FLAT_TABLE_NO_ROWS QA rule.
            new_blocks.append(block)
            continue

        table = TableBlock(
            block_id=block.block_id,
            bbox=bbox,
            children=list(row_blocks),
        )
        new_blocks.append(table)
        edges.append(
            AnchorEdge(
                edge_kind=AnchorEdgeKind.BLOCK_TO_REGION,
                source_id=block.block_id,
                target_id=best_candidate.evidence_id,
            )
        )

    return new_blocks, edges
