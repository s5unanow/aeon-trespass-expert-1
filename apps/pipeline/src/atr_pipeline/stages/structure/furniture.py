"""Furniture detection — detect repeated headers/footers across pages.

In production, this will analyze all pages to find repeated text
regions (page numbers, headers, footers) and mark them for removal.
Currently a pass-through for single-page documents.
"""

from __future__ import annotations

from atr_schemas.native_page_v1 import NativePageV1


class FurnitureMap:
    """Detected furniture regions for a document."""

    def __init__(self) -> None:
        self.stripped_word_ids: list[str] = []
        self.repeated_regions: list[dict[str, object]] = []

    @property
    def has_furniture(self) -> bool:
        return len(self.stripped_word_ids) > 0


def detect_furniture(pages: list[NativePageV1]) -> FurnitureMap:
    """Detect repeated furniture across document pages.

    For single-page documents (walking skeleton), returns empty results.
    Multi-page detection will use text repetition analysis across
    consistent Y-positions near page top/bottom.
    """
    result = FurnitureMap()

    if len(pages) < 2:
        return result

    # TODO: Implement cross-page repetition detection
    # 1. Cluster words by normalized Y-position (top/bottom zones)
    # 2. Find text that repeats across >50% of pages
    # 3. Mark those word_ids as furniture

    return result
