"""Furniture detection — detect repeated headers/footers across pages.

Analyzes all pages to find repeated text in consistent top/bottom zones
and marks matching span IDs for removal during structure recovery.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from atr_schemas.native_page_v1 import NativePageV1, SpanEvidence

# Page zones for furniture detection (PDF points, 792pt = standard A4 height)
_TOP_ZONE_MAX_Y = 60.0
_BOTTOM_ZONE_MIN_Y = 750.0

# Text appearing on >50% of pages is furniture
_REPETITION_THRESHOLD = 0.5

# Strip leading/trailing digits and whitespace for normalization
_PAGE_NUM_RE = re.compile(r"^\s*\d+\s*$")


@dataclass
class FurnitureRegion:
    """A detected furniture region across pages."""

    zone: str  # "top" or "bottom"
    text: str  # normalized text
    page_count: int  # number of pages where found


@dataclass
class FurnitureMap:
    """Detected furniture regions for a document."""

    stripped_span_ids: list[str] = field(default_factory=list)
    repeated_regions: list[FurnitureRegion] = field(default_factory=list)
    _span_id_set: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        if self.stripped_span_ids and not self._span_id_set:
            self._span_id_set = set(self.stripped_span_ids)

    def finalize(self) -> None:
        """Build lookup set from span IDs. Call after populating stripped_span_ids."""
        self._span_id_set = set(self.stripped_span_ids)

    @property
    def has_furniture(self) -> bool:
        return len(self.stripped_span_ids) > 0

    def is_furniture_span(self, span_id: str) -> bool:
        """Check if a span ID was detected as furniture."""
        return span_id in self._span_id_set


def _normalize_text(text: str) -> str:
    """Normalize span text for comparison — strip whitespace, lowercase."""
    return text.strip().lower()


def _is_zone_span(span: SpanEvidence, zone: str, page_height: float) -> bool:
    """Check if a span falls within a furniture zone."""
    if zone == "top":
        return span.bbox.y0 < _TOP_ZONE_MAX_Y
    # "bottom" — use page height if available, else absolute threshold
    threshold = (
        max(page_height - 42.0, _BOTTOM_ZONE_MIN_Y) if page_height > 0 else _BOTTOM_ZONE_MIN_Y
    )
    return span.bbox.y0 >= threshold


def _collect_zone_texts(
    pages: list[NativePageV1],
    zone: str,
) -> dict[str, list[tuple[str, str]]]:
    """Collect normalized text -> list of (page_id, span_id) per zone.

    Returns a mapping from normalized text to all page/span occurrences.
    """
    text_occurrences: dict[str, list[tuple[str, str]]] = {}
    for page in pages:
        page_height = page.dimensions_pt.height if page.dimensions_pt else 0.0
        for span in page.spans:
            if not _is_zone_span(span, zone, page_height):
                continue
            normalized = _normalize_text(span.text)
            if not normalized or _PAGE_NUM_RE.match(normalized):
                continue  # Skip pure page numbers and empty
            text_occurrences.setdefault(normalized, []).append(
                (page.page_id, span.span_id),
            )
    return text_occurrences


def detect_furniture(pages: list[NativePageV1]) -> FurnitureMap:
    """Detect repeated furniture across document pages.

    Algorithm:
    1. Collect text in top and bottom zones of each page
    2. Normalize text (strip whitespace, lowercase, ignore page numbers)
    3. Find text appearing on >=50% of pages
    4. Mark all matching span IDs as furniture
    """
    result = FurnitureMap()

    if len(pages) < 2:
        return result

    threshold = len(pages) * _REPETITION_THRESHOLD

    for zone in ("top", "bottom"):
        texts = _collect_zone_texts(pages, zone)
        for text, occurrences in texts.items():
            # Count unique pages (a text may appear in multiple spans per page)
            unique_pages = len({page_id for page_id, _ in occurrences})
            if unique_pages >= threshold:
                result.repeated_regions.append(
                    FurnitureRegion(zone=zone, text=text, page_count=unique_pages),
                )
                for _, span_id in occurrences:
                    result.stripped_span_ids.append(span_id)

    result.finalize()
    return result
