"""PatchSetV1 — human-reviewed deterministic patches."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PatchOperation(BaseModel):
    """A single patch operation."""

    op: str  # replace, insert, delete
    path: str  # JSON pointer or block reference
    value: object = None


class PatchSetV1(BaseModel):
    """A set of typed patches for a specific artifact."""

    schema_version: str = Field(default="patch_set.v1", pattern=r"^patch_set\.v\d+$")
    patch_id: str
    target_artifact_ref: str = ""
    operations: list[PatchOperation] = Field(default_factory=list)
    reason: str = ""
    author: str = ""
