"""BuildManifestV1 — published release manifest."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReleaseFile(BaseModel):
    """A file included in the release bundle."""

    path: str
    sha256: str = ""
    size_bytes: int = 0


class BuildManifestV1(BaseModel):
    """Manifest for a published static release."""

    schema_version: str = Field(default="build_manifest.v1", pattern=r"^build_manifest\.v\d+$")
    build_id: str
    document_id: str
    content_version: str = ""
    generated_at: str = ""
    pipeline_version: str = ""
    files: list[ReleaseFile] = Field(default_factory=list)
