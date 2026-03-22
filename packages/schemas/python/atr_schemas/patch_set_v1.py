"""PatchSetV1 — human-reviewed deterministic patches."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from atr_schemas.enums import PatchScope, PatchTargetKind


class PatchProvenance(BaseModel):
    """Tracks who/what created the patch and its expected confidence impact."""

    author: str = ""
    created_at: datetime | None = None
    source_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Page confidence before patch"
    )
    expected_confidence_delta: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Expected change in page confidence after patch",
    )


class PatchOperation(BaseModel):
    """A single patch operation."""

    op: str  # replace, insert, delete
    path: str  # JSON pointer or block reference
    value: object = None
    scope: PatchScope | None = Field(
        default=None, description="Classification of what this operation corrects"
    )


class PatchSetV1(BaseModel):
    """A set of typed patches for a specific artifact."""

    schema_version: str = Field(default="patch_set.v1", pattern=r"^patch_set\.v\d+$")
    patch_id: str
    target_artifact_ref: str = ""
    target_kind: PatchTargetKind | None = Field(
        default=None, description="Which artifact schema this patch targets"
    )
    operations: list[PatchOperation] = Field(default_factory=list)
    reason: str = ""
    author: str = ""
    provenance: PatchProvenance | None = None
