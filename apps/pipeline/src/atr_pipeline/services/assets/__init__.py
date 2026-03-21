"""Asset registry services — build and query the document-level asset registry."""

from atr_pipeline.services.assets.identity import (
    asset_class_id,
    occurrence_id,
)
from atr_pipeline.services.assets.registry import AssetRegistryBuilder
from atr_pipeline.services.assets.resolver import (
    ResolvedSymbolPlacement,
    SymbolResolverInput,
    build_symbol_refs,
    resolve_symbols,
)

__all__ = [
    "AssetRegistryBuilder",
    "ResolvedSymbolPlacement",
    "SymbolResolverInput",
    "asset_class_id",
    "build_symbol_refs",
    "occurrence_id",
    "resolve_symbols",
]
