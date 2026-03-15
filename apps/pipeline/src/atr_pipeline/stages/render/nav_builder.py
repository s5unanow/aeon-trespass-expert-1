"""Build navigation payload from render pages."""

from __future__ import annotations


def build_nav_payload(
    document_id: str,
    render_pages: list[dict[str, object]],
) -> dict[str, object]:
    """Build a nav.json payload from render page data.

    For the walking skeleton, this is a simple ordered list.
    """
    pages: list[dict[str, object]] = []
    for i, page_data in enumerate(render_pages):
        page_meta = page_data.get("page", {})
        pages.append({
            "page_id": page_meta.get("id", ""),  # type: ignore[union-attr]
            "title": page_meta.get("title", ""),  # type: ignore[union-attr]
            "source_page_number": page_meta.get("source_page_number", 0),  # type: ignore[union-attr]
            "prev": render_pages[i - 1]["page"]["id"] if i > 0 else None,  # type: ignore[index]
            "next": render_pages[i + 1]["page"]["id"] if i < len(render_pages) - 1 else None,  # type: ignore[index]
        })

    return {
        "document_id": document_id,
        "pages": pages,
    }
