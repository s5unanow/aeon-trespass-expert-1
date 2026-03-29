"""Visual symbol resolver — classify and place symbol matches on a page.

Consumes symbol detections and page evidence (spans, regions) to produce
typed symbol placements with anchor classification and insertion coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atr_schemas.common import Rect
from atr_schemas.enums import RegionKind, SymbolAnchorKind
from atr_schemas.native_page_v1 import SpanEvidence
from atr_schemas.resolved_page_v1 import ResolvedRegion, ResolvedSymbolRef
from atr_schemas.symbol_match_set_v1 import SymbolMatch

# Tolerance for grouping spans into lines and matching symbols to text.
# Slightly wider than the block builder's 3.0 to handle multi-column
# layouts where column baselines differ by a few points.
_LINE_TOLERANCE = 6.0

# Vertical proximity threshold for "near text" (block-attached)
_NEAR_TEXT_TOLERANCE = 15.0

# Minimum bbox area for small symbols in table regions
_TABLE_SMALL_AREA = 900.0


@dataclass
class SymbolResolverInput:
    """Bundled inputs for symbol resolution."""

    matches: list[SymbolMatch]
    spans: list[SpanEvidence]
    regions: list[ResolvedRegion]
    page_id: str


@dataclass
class ResolvedSymbolPlacement:
    """Output per resolved symbol — anchor type, position, and evidence."""

    match: SymbolMatch
    anchor_kind: SymbolAnchorKind
    containing_region: ResolvedRegion | None = None
    insertion_x: float | None = None
    block_spans: list[SpanEvidence] = field(default_factory=list)
    confidence: float = 1.0
    evidence_ids: list[str] = field(default_factory=list)


def resolve_symbols(inp: SymbolResolverInput) -> list[ResolvedSymbolPlacement]:
    """Resolve all symbol matches into typed placements.

    For each match:
    1. Find containing region
    2. Find nearest text line
    3. Classify anchor kind
    4. For INLINE, compute insertion_x
    """
    placements: list[ResolvedSymbolPlacement] = []
    for match in inp.matches:
        if not match.inline:
            continue

        region = _find_containing_region(match.bbox, inp.regions)
        line_spans = _find_nearest_text_line(match.bbox, inp.spans)
        anchor = _classify_anchor(match.bbox, region, line_spans)

        insertion_x: float | None = None
        if anchor == SymbolAnchorKind.INLINE and line_spans:
            insertion_x = _compute_insertion_x(match.bbox, line_spans)

        evidence: list[str] = []
        if region is not None:
            evidence.extend(region.evidence_ids)
        evidence.extend(s.span_id for s in line_spans)

        placements.append(
            ResolvedSymbolPlacement(
                match=match,
                anchor_kind=anchor,
                containing_region=region,
                insertion_x=insertion_x,
                block_spans=line_spans,
                confidence=match.score,
                evidence_ids=evidence,
            )
        )

    return placements


def build_symbol_refs(
    placements: list[ResolvedSymbolPlacement],
) -> list[ResolvedSymbolRef]:
    """Convert placements to schema-level ResolvedSymbolRef list."""
    return [
        ResolvedSymbolRef(
            symbol_id=p.match.symbol_id,
            instance_id=p.match.instance_id,
            anchor_kind=p.anchor_kind,
            evidence_ids=p.evidence_ids,
            bbox=p.match.bbox,
            confidence=p.confidence,
        )
        for p in placements
    ]


def _find_containing_region(
    bbox: Rect,
    regions: list[ResolvedRegion],
) -> ResolvedRegion | None:
    """Find the region whose bbox contains the symbol center."""
    cx = (bbox.x0 + bbox.x1) / 2
    cy = (bbox.y0 + bbox.y1) / 2

    for region in regions:
        rb = region.bbox
        if rb.x0 <= cx <= rb.x1 and rb.y0 <= cy <= rb.y1:
            return region
    return None


def _find_nearest_text_line(
    bbox: Rect,
    spans: list[SpanEvidence],
) -> list[SpanEvidence]:
    """Find spans on the nearest text line (within _LINE_TOLERANCE of the symbol's y center)."""
    if not spans:
        return []

    symbol_cy = (bbox.y0 + bbox.y1) / 2

    # Group spans by y-proximity into lines
    lines: list[list[SpanEvidence]] = []
    for span in sorted(spans, key=lambda s: s.bbox.y0):
        if lines and abs(span.bbox.y0 - lines[-1][0].bbox.y0) < _LINE_TOLERANCE:
            lines[-1].append(span)
        else:
            lines.append([span])

    # Find the line whose vertical center is closest to the symbol
    best_line: list[SpanEvidence] = []
    best_dist = float("inf")
    for line in lines:
        line_y0 = min(s.bbox.y0 for s in line)
        line_y1 = max(s.bbox.y1 for s in line)
        line_cy = (line_y0 + line_y1) / 2
        dist = abs(symbol_cy - line_cy)
        if dist < best_dist:
            best_dist = dist
            best_line = line

    # Only return if the symbol is vertically close enough
    if best_line:
        line_y0 = min(s.bbox.y0 for s in best_line)
        line_y1 = max(s.bbox.y1 for s in best_line)
        if bbox.y0 <= line_y1 + _LINE_TOLERANCE and bbox.y1 >= line_y0 - _LINE_TOLERANCE:
            return best_line

    return []


def _classify_anchor(
    bbox: Rect,
    region: ResolvedRegion | None,
    line_spans: list[SpanEvidence],
) -> SymbolAnchorKind:
    """Classify anchor type from region context and line proximity."""
    # MARGIN_NOTE region → REGION_ANNOTATION
    if region is not None and region.kind == RegionKind.MARGIN_NOTE:
        return SymbolAnchorKind.REGION_ANNOTATION

    # TABLE_AREA region + small bbox → CELL_LOCAL
    if region is not None and region.kind == RegionKind.TABLE_AREA:
        area = bbox.width * bbox.height
        if area < _TABLE_SMALL_AREA:
            return SymbolAnchorKind.CELL_LOCAL

    if not line_spans:
        return SymbolAnchorKind.REGION_ANNOTATION

    # Symbol is on a text line — check if PREFIX or INLINE
    line_x0 = min(s.bbox.x0 for s in line_spans)
    symbol_cx = (bbox.x0 + bbox.x1) / 2

    if symbol_cx < line_x0:
        return SymbolAnchorKind.PREFIX

    # Check if symbol overlaps the text line horizontally
    line_x1 = max(s.bbox.x1 for s in line_spans)

    if bbox.x0 <= line_x1 and bbox.x1 >= line_x0:
        return SymbolAnchorKind.INLINE

    # Near text but not overlapping → BLOCK_ATTACHED
    line_y0 = min(s.bbox.y0 for s in line_spans)
    line_y1 = max(s.bbox.y1 for s in line_spans)
    v_dist = min(abs(bbox.y0 - line_y1), abs(bbox.y1 - line_y0))
    if v_dist < _NEAR_TEXT_TOLERANCE:
        return SymbolAnchorKind.BLOCK_ATTACHED

    return SymbolAnchorKind.REGION_ANNOTATION


def _compute_insertion_x(
    bbox: Rect,
    line_spans: list[SpanEvidence],
) -> float:
    """Estimate character-level insertion x from span bboxes.

    Walks through spans estimating character positions as:
        char_x = span.bbox.x0 + (i / len(text)) * span_width

    Returns the x coordinate of the character gap closest to the symbol center.
    """
    symbol_cx = (bbox.x0 + bbox.x1) / 2

    # Build list of estimated character x-positions
    char_positions: list[float] = []
    for span in sorted(line_spans, key=lambda s: s.bbox.x0):
        text = span.text
        if not text:
            continue
        span_width = span.bbox.width
        for i in range(len(text)):
            char_x = span.bbox.x0 + (i / max(len(text), 1)) * span_width
            char_positions.append(char_x)
        # Add the end position
        char_positions.append(span.bbox.x1)

    if not char_positions:
        return symbol_cx

    # Find closest gap to symbol center
    best_x = char_positions[0]
    best_dist = abs(symbol_cx - best_x)
    for cx in char_positions[1:]:
        dist = abs(symbol_cx - cx)
        if dist < best_dist:
            best_dist = dist
            best_x = cx

    return best_x
