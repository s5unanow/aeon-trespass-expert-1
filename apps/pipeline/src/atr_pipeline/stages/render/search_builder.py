"""Build SearchDocsV1 from render pages."""

from __future__ import annotations

from atr_schemas.render_page_v1 import RenderPageV1
from atr_schemas.search_docs_v1 import SearchDocEntry, SearchDocsV1


def build_search_docs(
    document_id: str,
    render_pages: list[RenderPageV1],
) -> SearchDocsV1:
    """Build search documents from render pages."""
    docs: list[SearchDocEntry] = []

    for page in render_pages:
        # Extract plain text from all blocks
        texts: list[str] = []
        for block in page.blocks:
            if hasattr(block, "children"):
                for child in block.children:  # type: ignore[union-attr]
                    if child.kind == "text":  # type: ignore[union-attr]
                        texts.append(child.text)  # type: ignore[union-attr]

        raw_text = " ".join(texts)
        # Simple normalization: lowercase, split on whitespace
        terms = list({w.lower().strip(".,;:!?") for w in raw_text.split() if len(w) > 1})

        docs.append(
            SearchDocEntry(
                page_id=page.page.id,
                title=page.page.title,
                text=raw_text,
                normalized_terms=sorted(terms),
                section_path=list(page.page.section_path),
                source_page_number=page.page.source_page_number,
            )
        )

    return SearchDocsV1(document_id=document_id, docs=docs)
