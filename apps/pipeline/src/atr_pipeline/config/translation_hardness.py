"""Translation hardness-routing configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranslationHardnessWeights(BaseModel):
    """Weighted contribution of each deterministic hardness signal."""

    model_config = ConfigDict(extra="forbid")

    inline_icon_density: float = Field(default=1.0, ge=0.0)
    cross_reference_density: float = Field(default=1.0, ge=0.0)
    table_presence: float = Field(default=1.0, ge=0.0)
    segment_count: float = Field(default=0.5, ge=0.0)
    segment_length: float = Field(default=0.5, ge=0.0)


class TranslationHardnessConfig(BaseModel):
    """Config for deterministic translation model-hard routing."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    threshold: float = Field(default=1.0, ge=0.0)
    icon_density_reference: float = Field(default=0.20, gt=0.0)
    xref_density_reference: float = Field(default=0.10, gt=0.0)
    segment_count_reference: int = Field(default=24, ge=1)
    segment_length_reference: int = Field(default=1200, ge=1)
    weights: TranslationHardnessWeights = Field(default_factory=TranslationHardnessWeights)
