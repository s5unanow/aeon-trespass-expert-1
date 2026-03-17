"""Build navigation payload from render pages."""

from __future__ import annotations

from typing import Any


def build_nav_payload(
    document_id: str,
    render_pages: list[dict[str, Any]],
) -> dict[str, object]:
    """Build a nav.json payload from render page data.

    For the walking skeleton, this is a simple ordered list.
    """
    pages: list[dict[str, Any]] = []
    for i, page_data in enumerate(render_pages):
        page_meta = page_data.get("page", {})
        pages.append({
            "page_id": page_meta.get("id", ""),
            "title": page_meta.get("title", ""),
            "source_page_number": page_meta.get("source_page_number", 0),
            "prev": render_pages[i - 1]["page"]["id"] if i > 0 else None,
            "next": render_pages[i + 1]["page"]["id"] if i < len(render_pages) - 1 else None,
        })

    return {
        "document_id": document_id,
        "pages": pages,
    }
