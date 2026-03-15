"""Load a symbol catalog from TOML configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from atr_schemas.symbol_catalog_v1 import SymbolCatalogV1, SymbolEntry


def load_symbol_catalog(path: Path) -> SymbolCatalogV1:
    """Load a symbol catalog from a TOML file."""
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    symbols = [
        SymbolEntry(
            symbol_id=s["symbol_id"],
            label=s.get("label", ""),
            alt_label_ru=s.get("alt_label_ru", ""),
            template_asset=s.get("template_asset", ""),
            match_threshold=s.get("match_threshold", 0.93),
            inline=s.get("inline", True),
        )
        for s in raw.get("symbols", [])
    ]

    return SymbolCatalogV1(
        catalog_id=raw.get("catalog_id", ""),
        version=raw.get("version", ""),
        symbols=symbols,
    )
