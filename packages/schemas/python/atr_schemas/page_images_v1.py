"""PageImagesV1 — per-page manifest of images extracted from the source PDF.

Emitted by ``IngestStage`` after PDF image extraction; consumed by both
QA (for the dead-page-ref suppression manifest, S5U-730) and by future
exporter refactors that wish to avoid re-extracting on every web export.

Each manifest carries the page id and a list of every image extracted at
the ingest threshold.  Downstream consumers apply their own dimension
gates (e.g., the web exporter requires ``min_width=100, min_height=100``).
The contract is "what was extracted from the PDF" — not "what survives a
specific consumer's threshold."
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PageImageEntry(BaseModel):
    """One image extracted from the source PDF for a given page."""

    image_id: str = Field(
        description=(
            "Namespaced image id of the form ``p{page_number:04d}.img{idx:04d}`` "
            "matching the entity_id used by the ``image`` artifact family."
        ),
    )
    width_px: int = Field(ge=1, description="Decoded image width in pixels.")
    height_px: int = Field(ge=1, description="Decoded image height in pixels.")
    extension: str = Field(
        description="File extension including leading dot (e.g. ``.png``, ``.jpeg``).",
    )


class PageImagesV1(BaseModel):
    """Per-page manifest of source-PDF images, scoped to ``page``."""

    schema_version: str = Field(
        default="page_images.v1",
        pattern=r"^page_images\.v\d+$",
    )
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    images: list[PageImageEntry] = Field(default_factory=list)
