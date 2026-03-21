"""AssetClassV1 — unique visual identity for a reusable asset."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.enums import AssetSourceKind


class AssetIdentity(BaseModel):
    """Identity fingerprints for exact and fuzzy matching."""

    exact_hash: str = Field(
        default="",
        description="Content hash for exact identity (SHA-256 prefix for rasters, "
        "cluster hash for vectors).",
    )
    fuzzy_hash: str = Field(
        default="",
        description="Perceptual hash for near-duplicate matching.",
    )
    vector_signature: str = Field(
        default="",
        description="Canonical descriptor for vector-origin assets.",
    )


class AssetClassV1(BaseModel):
    """A unique visual entity that may appear one or more times across pages.

    Asset classes are deduplicated by identity: two occurrences with the same
    ``exact_hash`` collapse to one class.  Fuzzy identity enables
    near-duplicate grouping without requiring bit-exact matches.
    """

    schema_version: str = Field(
        default="asset_class.v1",
        pattern=r"^asset_class\.v\d+$",
    )
    class_id: str = Field(
        description="Stable identifier, e.g. ac.raster.deadbeef1234",
    )
    source_kind: AssetSourceKind
    identity: AssetIdentity = Field(default_factory=AssetIdentity)
    width_px: int = 0
    height_px: int = 0
    label: str = Field(
        default="",
        description="Human-readable label (e.g. symbol name from catalog).",
    )
    canonical_evidence_id: str = Field(
        default="",
        description="Evidence ID of the first occurrence that introduced this class.",
    )
