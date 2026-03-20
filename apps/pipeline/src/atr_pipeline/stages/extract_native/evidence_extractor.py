"""Orchestrate evidence extraction from a PDF page into PageEvidenceV1."""

from __future__ import annotations

from pathlib import Path

import fitz

from atr_schemas.common import PageDimensions
from atr_schemas.evidence_primitives_v1 import EvidenceEntity
from atr_schemas.page_evidence_v1 import EvidenceTransformMeta, PageEvidenceV1

from .evidence_text import extract_text_evidence
from .evidence_vectors import (
    extract_image_evidence,
    extract_table_evidence,
    extract_vector_evidence,
)


def extract_page_evidence(
    pdf_path: Path,
    *,
    page_number: int,
    document_id: str,
) -> PageEvidenceV1:
    """Extract all evidence primitives from a single PDF page.

    Produces chars, lines, text spans, image occurrences, vector paths,
    vector clusters, and table candidates.

    Args:
        pdf_path: Path to the PDF file.
        page_number: 1-based page number.
        document_id: Document identifier.

    Returns:
        PageEvidenceV1 with all observed evidence entities.
    """
    doc = fitz.open(str(pdf_path))
    page = doc[page_number - 1]
    page_rect = page.rect
    dims = PageDimensions(width=page_rect.width, height=page_rect.height)

    entities: list[EvidenceEntity] = []

    # Text evidence: chars, lines, spans
    chars, lines, spans = extract_text_evidence(page, dims)
    entities.extend(chars)
    entities.extend(lines)
    entities.extend(spans)

    # Image occurrences with content hashes
    entities.extend(extract_image_evidence(page, doc, dims))

    # Vector paths and clusters
    vector_paths, vector_clusters = extract_vector_evidence(page, dims)
    entities.extend(vector_paths)
    entities.extend(vector_clusters)

    # Table candidates
    entities.extend(extract_table_evidence(page, dims))

    doc.close()

    page_id = f"p{page_number:04d}"
    version_str: str = fitz.version[0] if isinstance(fitz.version[0], str) else str(fitz.version[0])
    return PageEvidenceV1(
        document_id=document_id,
        page_id=page_id,
        page_number=page_number,
        transform=EvidenceTransformMeta(
            extractor="pymupdf_evidence",
            extractor_version=version_str,
            page_dimensions_pt=dims,
            coordinate_space="pdf_points",
        ),
        entities=entities,
    )
