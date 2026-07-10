"""ImageSetManifestV1 — ordered raw photographed-page inputs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ImageMediaType = Literal["image/png", "image/jpeg"]
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class CaptureMetadataV1(BaseModel):
    """Capture and EXIF metadata retained with a photographed page."""

    captured_at: datetime | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    exif_orientation: int | None = Field(default=None, ge=1, le=8)


class ImageSetImageEntryV1(BaseModel):
    """One ordered image in an image-set input manifest."""

    image_id: str = Field(pattern=r"^img\.[a-z0-9][a-z0-9._-]*$")
    path: str = Field(min_length=1)
    media_type: ImageMediaType
    sha256: str = Field(pattern=SHA256_PATTERN)
    page_id: str = Field(pattern=r"^p\d{4}$")
    page_number: int = Field(ge=1)
    capture: CaptureMetadataV1 = Field(default_factory=CaptureMetadataV1)


class ImageSetManifestV1(BaseModel):
    """Ordered image-set source declaration."""

    schema_version: str = Field(
        default="image_set_manifest.v1",
        pattern=r"^image_set_manifest\.v\d+$",
    )
    images: list[ImageSetImageEntryV1] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_ordered_entries(self) -> ImageSetManifestV1:
        image_ids = [entry.image_id for entry in self.images]
        if len(image_ids) != len(set(image_ids)):
            msg = "duplicate image_id in image-set manifest"
            raise ValueError(msg)

        paths = [entry.path for entry in self.images]
        if len(paths) != len(set(paths)):
            msg = "duplicate image path in image-set manifest"
            raise ValueError(msg)

        page_ids = [entry.page_id for entry in self.images]
        if len(page_ids) != len(set(page_ids)):
            msg = "duplicate page mapping in image-set manifest"
            raise ValueError(msg)

        expected_numbers = list(range(1, len(self.images) + 1))
        actual_numbers = [entry.page_number for entry in self.images]
        if actual_numbers != expected_numbers:
            msg = "image-set page numbers must be contiguous and ordered from 1"
            raise ValueError(msg)

        for entry in self.images:
            expected_page_id = f"p{entry.page_number:04d}"
            if entry.page_id != expected_page_id:
                msg = (
                    f"page_id {entry.page_id!r} must match page_number "
                    f"{entry.page_number} ({expected_page_id!r})"
                )
                raise ValueError(msg)
        return self
