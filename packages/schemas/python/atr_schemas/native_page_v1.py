"""NativePageV1 — native PDF text/image evidence per page."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.common import PageDimensions, Rect


class WordEvidence(BaseModel):
    """A single word extracted from the PDF."""

    word_id: str
    text: str
    bbox: Rect
    font_name: str = ""
    font_size: float = 0.0
    flags: int = 0


class SpanEvidence(BaseModel):
    """A text span with consistent formatting."""

    span_id: str
    text: str
    bbox: Rect
    font_name: str = ""
    font_size: float = 0.0
    flags: int = 0
    color: int = 0


class ImageBlockEvidence(BaseModel):
    """An image object found in the PDF page."""

    image_id: str
    bbox: Rect
    width_px: int = 0
    height_px: int = 0
    colorspace: str = ""
    xref: int = 0


class NativePageV1(BaseModel):
    """Native text and image evidence for a single page."""

    schema_version: str = Field(default="native_page.v1", pattern=r"^native_page\.v\d+$")
    document_id: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    dimensions_pt: PageDimensions
    words: list[WordEvidence] = Field(default_factory=list)
    spans: list[SpanEvidence] = Field(default_factory=list)
    image_blocks: list[ImageBlockEvidence] = Field(default_factory=list)
    extractor_meta: dict[str, str] = Field(default_factory=dict)
