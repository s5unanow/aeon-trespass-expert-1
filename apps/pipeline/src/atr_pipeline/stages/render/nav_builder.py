"""Build navigation payload from render pages."""

from __future__ import annotations

from atr_schemas.nav_payload_v1 import NavEntryV1, NavPayloadV1
from atr_schemas.render_page_v1 import RenderPageV1


def build_nav_payload(
    document_id: str,
    render_pages: list[RenderPageV1],
) -> NavPayloadV1:
    """Build a typed nav payload from render pages."""
    entries: list[NavEntryV1] = []
    for i, page in enumerate(render_pages):
        entries.append(
            NavEntryV1(
                page_id=page.page.id,
                title=page.page.title,
                source_page_number=page.page.source_page_number,
                prev=render_pages[i - 1].page.id if i > 0 else None,
                next=render_pages[i + 1].page.id if i < len(render_pages) - 1 else None,
            )
        )

    return NavPayloadV1(document_id=document_id, pages=entries)
