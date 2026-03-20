"""Difficulty scoring — classify page complexity from native evidence."""

from __future__ import annotations

from atr_schemas.layout_page_v1 import DifficultyScoreV1, LayoutZone
from atr_schemas.native_page_v1 import NativePageV1

# Thresholds for hard-page classification
_LOW_TEXT_COVERAGE = 0.30
_LOW_AGREEMENT = 0.90


def compute_difficulty(
    native: NativePageV1,
    zones: list[LayoutZone],
) -> DifficultyScoreV1:
    """Score page difficulty from native evidence and layout zones.

    Returns a ``DifficultyScoreV1`` with ``hard_page`` and
    ``recommended_route`` set according to heuristic thresholds.
    """
    dims = native.dimensions_pt
    page_area = dims.width * dims.height

    # --- native text coverage ---
    text_area = sum(
        max(0, w.bbox.x1 - w.bbox.x0) * max(0, w.bbox.y1 - w.bbox.y0) for w in native.words
    )
    native_text_coverage = min(text_area / page_area, 1.0) if page_area > 0 else 0.0

    # --- column detection ---
    column_count = _detect_columns(native)

    # --- zone overlap ratio ---
    zone_overlap_ratio = _zone_overlap(zones) if len(zones) >= 2 else 0.0

    # --- extractor agreement (stub until second extractor exists) ---
    extractor_agreement = 1.0

    # --- routing decision ---
    hard_page = False
    route = "R1"

    if native_text_coverage < _LOW_TEXT_COVERAGE or column_count > 1:
        hard_page = True
        route = "R2"
    elif extractor_agreement < _LOW_AGREEMENT:
        hard_page = True
        route = "R3"

    return DifficultyScoreV1(
        page_id=native.page_id,
        column_count=column_count,
        zone_overlap_ratio=zone_overlap_ratio,
        native_text_coverage=round(native_text_coverage, 4),
        extractor_agreement=extractor_agreement,
        hard_page=hard_page,
        recommended_route=route,
    )


def _detect_columns(native: NativePageV1) -> int:
    """Estimate column count from word x-positions.

    Looks for a clear vertical gap in the middle of the page where
    there are significant word clusters on both sides.
    """
    if len(native.words) < 10:
        return 1

    page_width = native.dimensions_pt.width
    if page_width <= 0:
        return 1

    # Build histogram of word center-x positions (10 bins)
    n_bins = 10
    bin_width = page_width / n_bins
    counts = [0] * n_bins
    for w in native.words:
        cx = (w.bbox.x0 + w.bbox.x1) / 2
        idx = max(0, min(int(cx / bin_width), n_bins - 1))
        counts[idx] += 1

    total = sum(counts)
    if total == 0:
        return 1

    # Look for a gap in the middle third with significant words on both sides
    third = n_bins // 3
    threshold = total * 0.02  # Gap bin must have <2% of total words
    for i in range(third, n_bins - third):
        if counts[i] < threshold:
            left = sum(counts[:i])
            right = sum(counts[i + 1 :])
            if left >= total * 0.2 and right >= total * 0.2:
                return 2

    return 1


def _zone_overlap(zones: list[LayoutZone]) -> float:
    """Fraction of zone pairs that overlap."""
    n = len(zones)
    if n < 2:
        return 0.0

    overlaps = 0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            pairs += 1
            a, b = zones[i].bbox, zones[j].bbox
            if a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1:
                overlaps += 1

    return overlaps / pairs if pairs > 0 else 0.0
