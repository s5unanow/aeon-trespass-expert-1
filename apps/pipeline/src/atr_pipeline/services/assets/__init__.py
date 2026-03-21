"""Asset registry services — build and query the document-level asset registry."""

from atr_pipeline.services.assets.identity import (
    asset_class_id,
    occurrence_id,
)
from atr_pipeline.services.assets.registry import AssetRegistryBuilder

__all__ = [
    "AssetRegistryBuilder",
    "asset_class_id",
    "occurrence_id",
]
