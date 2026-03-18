"""Build SourceManifestV1 from PDF fingerprint data."""

from __future__ import annotations

from atr_schemas.source_manifest_v1 import PageEntry, SourceManifestV1


def build_manifest(
    *,
    document_id: str,
    source_pdf_sha256: str,
    page_count: int,
) -> SourceManifestV1:
    """Create a SourceManifestV1 with page entries."""
    pages = [PageEntry(page_id=f"p{i:04d}", page_number=i) for i in range(1, page_count + 1)]
    return SourceManifestV1(
        document_id=document_id,
        source_pdf_sha256=source_pdf_sha256,
        page_count=page_count,
        pages=pages,
    )
