"""Identity helpers for asset class and occurrence IDs."""

from __future__ import annotations

from atr_schemas.enums import AssetSourceKind

_KIND_PREFIX: dict[AssetSourceKind, str] = {
    AssetSourceKind.EMBEDDED_RASTER: "raster",
    AssetSourceKind.VECTOR_CLUSTER: "vector",
    AssetSourceKind.RENDERED_CROP: "crop",
}


def asset_class_id(source_kind: AssetSourceKind, exact_hash: str) -> str:
    """Derive a deterministic class ID from source kind and content hash.

    Format: ``ac.{kind_prefix}.{hash_prefix}`` where *hash_prefix* is the
    first 12 hex characters of *exact_hash*.
    """
    prefix = _KIND_PREFIX[source_kind]
    short = exact_hash[:12] if exact_hash else "0" * 12
    return f"ac.{prefix}.{short}"


def occurrence_id(page_id: str, seq: int) -> str:
    """Build a page-scoped occurrence ID.

    Format: ``ao.{page_id}.{seq:03d}``
    """
    return f"ao.{page_id}.{seq:03d}"
