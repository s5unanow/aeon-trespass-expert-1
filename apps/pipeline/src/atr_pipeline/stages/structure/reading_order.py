"""Reading-order graph — linearize regions and emit anchored-aside edges.

Consumes :class:`ResolvedRegion` entries from region-graph segmentation and
produces a deterministic reading order plus aside-to-main anchor edges.
The output populates ``main_flow_order`` and ``anchor_edges`` on
:class:`ResolvedPageV1`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from atr_schemas.enums import AnchorEdgeKind, RegionKind
from atr_schemas.resolved_page_v1 import AnchorEdge, ResolvedRegion

# Region kinds that form the main reading flow.
_MAIN_FLOW_KINDS: frozenset[RegionKind] = frozenset(
    {
        RegionKind.BODY,
        RegionKind.TABLE_AREA,
        RegionKind.FIGURE_AREA,
        RegionKind.FULL_WIDTH,
        RegionKind.UNKNOWN,
    }
)

# Region kinds that are anchored asides (not in main flow).
_ASIDE_KINDS: frozenset[RegionKind] = frozenset(
    {
        RegionKind.SIDEBAR,
        RegionKind.CALLOUT_AREA,
        RegionKind.MARGIN_NOTE,
    }
)

# Region kinds excluded from reading order entirely.
_FURNITURE_KINDS: frozenset[RegionKind] = frozenset(
    {
        RegionKind.HEADER,
        RegionKind.FOOTER,
    }
)

# Minimum vertical overlap fraction to group regions in the same band.
_BAND_OVERLAP_THRESHOLD = 0.5


@dataclass
class ReadingOrderResult:
    """Output of reading-order computation."""

    main_flow_order: list[str] = field(default_factory=list)
    anchor_edges: list[AnchorEdge] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class _Band:
    """A horizontal slice containing vertically-overlapping regions."""

    y0: float
    y1: float
    main_regions: list[ResolvedRegion] = field(default_factory=list)
    aside_regions: list[ResolvedRegion] = field(default_factory=list)


def compute_reading_order(
    regions: list[ResolvedRegion],
) -> ReadingOrderResult:
    """Compute reading order from segmented regions.

    Returns region IDs in main-flow reading order and aside-to-main
    anchor edges for sidebar / callout / margin-note regions.
    """
    if not regions:
        return ReadingOrderResult()

    main_regions, aside_regions = _partition_regions(regions)
    if not main_regions:
        return ReadingOrderResult(confidence=0.5)

    bands = _group_into_bands(main_regions, aside_regions)
    ordered_ids = _linearize_bands(bands)
    edges = _build_aside_edges(bands)
    confidence = _compute_confidence(bands, aside_regions)

    return ReadingOrderResult(
        main_flow_order=ordered_ids,
        anchor_edges=edges,
        confidence=confidence,
    )


def _partition_regions(
    regions: list[ResolvedRegion],
) -> tuple[list[ResolvedRegion], list[ResolvedRegion]]:
    """Split regions into main-flow and aside, discarding furniture."""
    main: list[ResolvedRegion] = []
    aside: list[ResolvedRegion] = []
    for r in regions:
        if r.kind in _FURNITURE_KINDS:
            continue
        if r.kind in _ASIDE_KINDS:
            aside.append(r)
        else:
            main.append(r)
    return main, aside


def _regions_overlap_vertically(
    r: ResolvedRegion,
    band_y0: float,
    band_y1: float,
) -> bool:
    """Check if a region overlaps a band by at least the threshold fraction."""
    overlap_top = max(r.bbox.y0, band_y0)
    overlap_bot = min(r.bbox.y1, band_y1)
    overlap = max(0.0, overlap_bot - overlap_top)
    region_height = r.bbox.y1 - r.bbox.y0
    if region_height <= 0:
        return False
    return overlap / region_height >= _BAND_OVERLAP_THRESHOLD


def _group_into_bands(
    main_regions: list[ResolvedRegion],
    aside_regions: list[ResolvedRegion],
) -> list[_Band]:
    """Group regions into horizontal bands by vertical overlap."""
    sorted_main = sorted(main_regions, key=lambda r: r.bbox.y0)
    bands: list[_Band] = []

    for region in sorted_main:
        placed = False
        for band in bands:
            if _regions_overlap_vertically(region, band.y0, band.y1):
                band.main_regions.append(region)
                band.y0 = min(band.y0, region.bbox.y0)
                band.y1 = max(band.y1, region.bbox.y1)
                placed = True
                break
        if not placed:
            bands.append(
                _Band(
                    y0=region.bbox.y0,
                    y1=region.bbox.y1,
                    main_regions=[region],
                )
            )

    # Sort bands top-to-bottom
    bands.sort(key=lambda b: b.y0)

    # Assign aside regions to their best-matching band
    for aside in aside_regions:
        best_band = _find_best_band(aside, bands)
        if best_band is not None:
            best_band.aside_regions.append(aside)

    return bands


def _find_best_band(
    region: ResolvedRegion,
    bands: list[_Band],
) -> _Band | None:
    """Find the band with the most vertical overlap for an aside region."""
    if not bands:
        return None
    best: _Band | None = None
    best_overlap = 0.0
    for band in bands:
        overlap_top = max(region.bbox.y0, band.y0)
        overlap_bot = min(region.bbox.y1, band.y1)
        overlap = max(0.0, overlap_bot - overlap_top)
        if overlap > best_overlap:
            best_overlap = overlap
            best = band

    # If no direct overlap, anchor to nearest band above (or first band)
    if best is None:
        cy = (region.bbox.y0 + region.bbox.y1) / 2
        nearest = bands[0]
        nearest_dist = abs(cy - (nearest.y0 + nearest.y1) / 2)
        for band in bands[1:]:
            dist = abs(cy - (band.y0 + band.y1) / 2)
            if dist < nearest_dist:
                nearest = band
                nearest_dist = dist
        best = nearest

    return best


def _linearize_bands(bands: list[_Band]) -> list[str]:
    """Produce main-flow region IDs in reading order: top-to-bottom, L-to-R."""
    ordered: list[str] = []
    for band in bands:
        sorted_regions = sorted(band.main_regions, key=lambda r: r.bbox.x0)
        ordered.extend(r.region_id for r in sorted_regions)
    return ordered


def _build_aside_edges(bands: list[_Band]) -> list[AnchorEdge]:
    """Create ASIDE_TO_MAIN edges linking aside regions to main-flow regions."""
    edges: list[AnchorEdge] = []
    for band in bands:
        if not band.main_regions:
            continue
        for aside in band.aside_regions:
            target = _nearest_main_region(aside, band.main_regions)
            edges.append(
                AnchorEdge(
                    edge_kind=AnchorEdgeKind.ASIDE_TO_MAIN,
                    source_id=aside.region_id,
                    target_id=target.region_id,
                    confidence=min(aside.confidence, target.confidence),
                )
            )
    return edges


def _nearest_main_region(
    aside: ResolvedRegion,
    main_regions: list[ResolvedRegion],
) -> ResolvedRegion:
    """Find the main-flow region closest to an aside region."""
    aside_cx = (aside.bbox.x0 + aside.bbox.x1) / 2
    aside_cy = (aside.bbox.y0 + aside.bbox.y1) / 2
    best = main_regions[0]
    best_dist = _distance(aside_cx, aside_cy, best)
    for r in main_regions[1:]:
        d = _distance(aside_cx, aside_cy, r)
        if d < best_dist:
            best = r
            best_dist = d
    return best


def _distance(cx: float, cy: float, region: ResolvedRegion) -> float:
    """Euclidean distance from a point to the centre of a region."""
    rcx = (region.bbox.x0 + region.bbox.x1) / 2
    rcy = (region.bbox.y0 + region.bbox.y1) / 2
    return math.sqrt((cx - rcx) ** 2 + (cy - rcy) ** 2)


def _compute_confidence(
    bands: list[_Band],
    aside_regions: list[ResolvedRegion],
) -> float:
    """Estimate reading-order confidence from layout complexity."""
    conf = 1.0

    # Multi-column bands reduce confidence
    multi_col_bands = sum(1 for b in bands if len(b.main_regions) > 1)
    conf -= multi_col_bands * 0.1

    # Many bands reduce confidence slightly
    if len(bands) > 1:
        conf -= (len(bands) - 1) * 0.03

    # Presence of asides adds uncertainty
    if aside_regions:
        conf -= 0.05

    return max(0.3, min(1.0, conf))
