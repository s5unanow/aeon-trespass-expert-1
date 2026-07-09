"""ImageSetManifestV1 — ordered raw image source manifest."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

JsonScalar = str | int | float | bool | None


class ImageSetImageV1(BaseModel):
    """Metadata for one raw source image."""

    image_id: str = Field(pattern=r"^img\.p\d{4}\.[0-9a-f]{12}$")
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    path: str = Field(min_length=1)
    media_type: Literal["image/png", "image/jpeg"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture: dict[str, JsonScalar] = Field(default_factory=dict)
    exif: dict[str, JsonScalar] = Field(default_factory=dict)


class ImageSetManifestV1(BaseModel):
    """Authoritative ordered mapping from source pages to raw image files."""

    schema_version: str = Field(
        default="image_set_manifest.v1",
        pattern=r"^image_set_manifest\.v\d+$",
    )
    source_kind: Literal["image_set"] = "image_set"
    images: list[ImageSetImageV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_order_and_uniqueness(self) -> ImageSetManifestV1:
        seen_ids: set[str] = set()
        seen_pages: set[str] = set()
        seen_entries: set[tuple[str, str]] = set()
        previous_page_number = 0
        for image in self.images:
            if image.image_id in seen_ids:
                msg = f"duplicate image_id: {image.image_id}"
                raise ValueError(msg)
            seen_ids.add(image.image_id)

            if image.page_number <= previous_page_number:
                msg = "images must be ordered by strictly increasing page_number"
                raise ValueError(msg)
            previous_page_number = image.page_number

            expected_page_id = f"p{image.page_number:04d}"
            if image.page_id != expected_page_id:
                msg = f"page_id {image.page_id!r} must match page_number {image.page_number}"
                raise ValueError(msg)

            if image.page_id in seen_pages:
                msg = f"duplicate page_id: {image.page_id}"
                raise ValueError(msg)
            seen_pages.add(image.page_id)

            entry_key = (image.page_id, image.path)
            if entry_key in seen_entries:
                msg = f"duplicate manifest entry: {image.page_id} {image.path}"
                raise ValueError(msg)
            seen_entries.add(entry_key)
        return self
