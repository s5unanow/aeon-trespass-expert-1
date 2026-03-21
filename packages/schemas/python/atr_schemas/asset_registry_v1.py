"""AssetRegistryV1 — document-level container for asset classes and occurrences."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.asset_class_v1 import AssetClassV1
from atr_schemas.asset_occurrence_v1 import AssetOccurrenceV1


class AssetRegistryV1(BaseModel):
    """Document-wide registry mapping asset classes to their page occurrences.

    Consumers (symbol resolver, figure resolver) query this registry instead
    of reaching into ad-hoc page-local data.
    """

    schema_version: str = Field(
        default="asset_registry.v1",
        pattern=r"^asset_registry\.v\d+$",
    )
    document_id: str
    classes: list[AssetClassV1] = Field(default_factory=list)
    occurrences: list[AssetOccurrenceV1] = Field(default_factory=list)

    def get_class(self, class_id: str) -> AssetClassV1 | None:
        """Look up an asset class by ID."""
        for c in self.classes:
            if c.class_id == class_id:
                return c
        return None

    def get_occurrences_for_class(self, class_id: str) -> list[AssetOccurrenceV1]:
        """Return all occurrences of a given asset class."""
        return [o for o in self.occurrences if o.class_id == class_id]

    def get_occurrences_for_page(self, page_id: str) -> list[AssetOccurrenceV1]:
        """Return all occurrences on a specific page."""
        return [o for o in self.occurrences if o.page_id == page_id]
