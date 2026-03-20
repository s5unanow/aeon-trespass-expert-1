"""Region graph segmentation — deterministic page topology from evidence.

Segments a page into typed regions (body, sidebar, header, footer, figure,
table, callout, full-width) using spatial analysis of evidence entities.
Produces :class:`ResolvedRegion` entries for downstream reading-order and
block assignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from atr_pipeline.config.models import StructureConfig
from atr_schemas.common import NormRect, PageDimensions, Rect
from atr_schemas.enums import RegionKind
from atr_schemas.evidence_primitives_v1 import (
    EvidenceImageOccurrence,
    EvidenceLine,
    EvidenceTableCandidate,
    EvidenceTextSpan,
    EvidenceVectorCluster,
)
from atr_schemas.page_evidence_v1 import PageEvidenceV1
from atr_schemas.resolved_page_v1 import ResolvedRegion


@dataclass
class _SpatialItem:
    """Lightweight bbox + category wrapper for an evidence entity."""

    evidence_id: str
    bbox: Rect
    category: str  # "text", "image", "vector", "table"


@dataclass
class _Band:
    """A horizontal slice of the page between full-width boundaries."""

    y0: float
    y1: float
    items: list[_SpatialItem] = field(default_factory=list)


def segment_regions(
    evidence: PageEvidenceV1,
    cfg: StructureConfig,
) -> list[ResolvedRegion]:
    """Segment a page into typed regions from raw evidence."""
    dims = evidence.transform.page_dimensions_pt
    items = _collect_spatial_items(evidence)
    if not items:
        return []

    regions: list[ResolvedRegion] = []
    region_idx = 0

    # 1. Furniture zones (header / footer)
    furniture_items: list[_SpatialItem] = []
    content_items: list[_SpatialItem] = []
    for item in items:
        if item.bbox.y1 <= cfg.furniture_top_max_y or item.bbox.y0 >= cfg.furniture_bottom_min_y:
            furniture_items.append(item)
        else:
            content_items.append(item)

    region_idx = _emit_furniture_regions(
        furniture_items,
        dims,
        cfg,
        regions,
        region_idx,
    )
    if not content_items:
        return regions

    # 2. Identify full-width elements that create band boundaries
    full_width: list[_SpatialItem] = []
    remaining: list[_SpatialItem] = []
    page_width = dims.width
    for item in content_items:
        item_width = item.bbox.x1 - item.bbox.x0
        if (
            item.category in ("image", "vector", "table")
            and page_width > 0
            and item_width / page_width >= cfg.full_width_fraction
        ):
            full_width.append(item)
        else:
            remaining.append(item)

    # 3. Full-width elements become their own regions
    for fw in full_width:
        region_idx += 1
        kind = _classify_full_width(fw)
        regions.append(_make_region(region_idx, kind, fw.bbox, [fw.evidence_id], dims))

    # 4. Split remaining content into horizontal bands
    bands = _split_into_bands(remaining, full_width, dims, cfg)

    # 5. Per-band column detection and region emission
    for band in bands:
        if not band.items:
            continue
        columns = _detect_columns_in_band(band, dims, cfg)
        for col_items in columns:
            region_idx += 1
            kind = _classify_column(col_items, dims)
            bbox = _union_items(col_items)
            eids = [it.evidence_id for it in col_items]
            confidence = _column_confidence(col_items)
            regions.append(_make_region(region_idx, kind, bbox, eids, dims, confidence))

    return regions


def _collect_spatial_items(evidence: PageEvidenceV1) -> list[_SpatialItem]:
    """Extract spatial items from evidence entities worth segmenting."""
    items: list[_SpatialItem] = []
    for ent in evidence.entities:
        if isinstance(ent, (EvidenceLine, EvidenceTextSpan)):
            items.append(_SpatialItem(ent.evidence_id, ent.bbox, "text"))
        elif isinstance(ent, EvidenceImageOccurrence):
            items.append(_SpatialItem(ent.evidence_id, ent.bbox, "image"))
        elif isinstance(ent, EvidenceVectorCluster):
            items.append(_SpatialItem(ent.evidence_id, ent.bbox, "vector"))
        elif isinstance(ent, EvidenceTableCandidate):
            items.append(_SpatialItem(ent.evidence_id, ent.bbox, "table"))
    return items


def _emit_furniture_regions(
    items: list[_SpatialItem],
    dims: PageDimensions,
    cfg: StructureConfig,
    regions: list[ResolvedRegion],
    start_idx: int,
) -> int:
    """Create HEADER/FOOTER regions from furniture-zone items. Returns next idx."""
    top = [it for it in items if it.bbox.y1 <= cfg.furniture_top_max_y]
    bottom = [it for it in items if it.bbox.y0 >= cfg.furniture_bottom_min_y]
    idx = start_idx
    if top:
        idx += 1
        bbox = _union_items(top)
        eids = [it.evidence_id for it in top]
        regions.append(_make_region(idx, RegionKind.HEADER, bbox, eids, dims, 0.9))
    if bottom:
        idx += 1
        bbox = _union_items(bottom)
        eids = [it.evidence_id for it in bottom]
        regions.append(_make_region(idx, RegionKind.FOOTER, bbox, eids, dims, 0.9))
    return idx


def _split_into_bands(
    items: list[_SpatialItem],
    full_width: list[_SpatialItem],
    dims: PageDimensions,
    cfg: StructureConfig,
) -> list[_Band]:
    """Split content into horizontal bands separated by full-width elements."""
    boundaries: list[float] = [cfg.furniture_top_max_y]
    for fw in sorted(full_width, key=lambda it: it.bbox.y0):
        boundaries.append(fw.bbox.y0)
        boundaries.append(fw.bbox.y1)
    boundaries.append(cfg.furniture_bottom_min_y)

    # Also detect large vertical gaps in content
    if items:
        sorted_by_y = sorted(items, key=lambda it: it.bbox.y0)
        prev_bottom = cfg.furniture_top_max_y
        for it in sorted_by_y:
            gap = it.bbox.y0 - prev_bottom
            if gap >= cfg.band_gap_min_pt:
                boundaries.append(prev_bottom)
                boundaries.append(it.bbox.y0)
            prev_bottom = max(prev_bottom, it.bbox.y1)

    boundaries = sorted(set(boundaries))

    # Build bands from consecutive boundary pairs
    bands: list[_Band] = []
    for i in range(0, len(boundaries) - 1, 2):
        y0 = boundaries[i]
        y1 = boundaries[i + 1] if i + 1 < len(boundaries) else dims.height
        band = _Band(y0=y0, y1=y1)
        for it in items:
            if _item_in_band(it, y0, y1):
                band.items.append(it)
        if band.items:
            bands.append(band)

    # Catch items not assigned to any band
    assigned = {id(it) for b in bands for it in b.items}
    unassigned = [it for it in items if id(it) not in assigned]
    if unassigned:
        bbox = _union_items(unassigned)
        bands.append(_Band(y0=bbox.y0, y1=bbox.y1, items=unassigned))

    return bands


def _item_in_band(item: _SpatialItem, y0: float, y1: float) -> bool:
    """Check if an item's vertical centre falls within a band."""
    cy = (item.bbox.y0 + item.bbox.y1) / 2
    return y0 <= cy <= y1


def _detect_columns_in_band(
    band: _Band,
    dims: PageDimensions,
    cfg: StructureConfig,
) -> list[list[_SpatialItem]]:
    """Detect columns within a band via x-position histogram gaps."""
    if len(band.items) < 2 or dims.width <= 0:
        return [band.items]

    n_bins = 20
    bin_width = dims.width / n_bins
    bins: list[list[_SpatialItem]] = [[] for _ in range(n_bins)]
    for it in band.items:
        cx = (it.bbox.x0 + it.bbox.x1) / 2
        idx = max(0, min(int(cx / bin_width), n_bins - 1))
        bins[idx].append(it)

    # Find gutter: empty bin(s) in the middle third with content on both sides
    third = n_bins // 3
    gutter_x = -1.0
    for i in range(third, n_bins - third):
        if not bins[i]:
            j = i
            while j < n_bins - third and not bins[j]:
                j += 1
            gutter_width_pt = (j - i) * bin_width
            if gutter_width_pt >= cfg.gutter_min_width_pt:
                left_count = sum(len(b) for b in bins[:i])
                right_count = sum(len(b) for b in bins[j:])
                total = len(band.items)
                if left_count >= total * 0.15 and right_count >= total * 0.15:
                    gutter_x = i * bin_width
                    break

    if gutter_x < 0:
        return [band.items]

    left = [it for it in band.items if (it.bbox.x0 + it.bbox.x1) / 2 < gutter_x]
    right = [it for it in band.items if (it.bbox.x0 + it.bbox.x1) / 2 >= gutter_x]
    result: list[list[_SpatialItem]] = []
    if left:
        result.append(left)
    if right:
        result.append(right)
    return result if result else [band.items]


def _classify_full_width(item: _SpatialItem) -> RegionKind:
    """Classify a full-width element."""
    if item.category == "table":
        return RegionKind.TABLE_AREA
    if item.category == "image":
        return RegionKind.FIGURE_AREA
    return RegionKind.FULL_WIDTH


def _classify_column(items: list[_SpatialItem], dims: PageDimensions) -> RegionKind:
    """Classify a column region by its content composition."""
    if not items:
        return RegionKind.UNKNOWN
    text_count = sum(1 for it in items if it.category == "text")
    image_count = sum(1 for it in items if it.category == "image")
    table_count = sum(1 for it in items if it.category == "table")
    total = len(items)

    if table_count > 0 and table_count >= total * 0.5:
        return RegionKind.TABLE_AREA
    if image_count > 0 and image_count >= total * 0.5 and text_count < 3:
        return RegionKind.FIGURE_AREA

    # Sidebar: narrow column (< 35% page width)
    bbox = _union_items(items)
    col_width = bbox.x1 - bbox.x0
    if dims.width > 0 and col_width / dims.width < 0.35 and text_count >= 1:
        return RegionKind.SIDEBAR

    if text_count > 0:
        return RegionKind.BODY
    return RegionKind.UNKNOWN


def _column_confidence(items: list[_SpatialItem]) -> float:
    """Estimate segmentation confidence for a column region."""
    if not items:
        return 0.5
    n = len(items)
    if n >= 5:
        return 0.9
    if n >= 2:
        return 0.8
    return 0.7


def _union_items(items: list[_SpatialItem]) -> Rect:
    """Compute the bounding union of a list of spatial items."""
    first = items[0].bbox
    x0, y0, x1, y1 = first.x0, first.y0, first.x1, first.y1
    for it in items[1:]:
        x0 = min(x0, it.bbox.x0)
        y0 = min(y0, it.bbox.y0)
        x1 = max(x1, it.bbox.x1)
        y1 = max(y1, it.bbox.y1)
    return Rect(x0=x0, y0=y0, x1=x1, y1=y1)


def _normalize_rect(rect: Rect, dims: PageDimensions) -> NormRect:
    """Convert PDF-point rect to normalised [0,1] space, clamped."""
    return NormRect(
        x0=max(0.0, min(1.0, rect.x0 / dims.width)) if dims.width else 0.0,
        y0=max(0.0, min(1.0, rect.y0 / dims.height)) if dims.height else 0.0,
        x1=max(0.0, min(1.0, rect.x1 / dims.width)) if dims.width else 0.0,
        y1=max(0.0, min(1.0, rect.y1 / dims.height)) if dims.height else 0.0,
    )


def _make_region(
    idx: int,
    kind: RegionKind,
    bbox: Rect,
    evidence_ids: list[str],
    dims: PageDimensions,
    confidence: float = 1.0,
) -> ResolvedRegion:
    """Construct a ResolvedRegion with proper ID and normalised bbox."""
    return ResolvedRegion(
        region_id=f"r{idx:03d}",
        kind=kind,
        bbox=bbox,
        norm_bbox=_normalize_rect(bbox, dims),
        evidence_ids=evidence_ids,
        confidence=confidence,
    )
