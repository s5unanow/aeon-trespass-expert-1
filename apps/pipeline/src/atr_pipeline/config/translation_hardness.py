"""Configuration for deterministic translation hardness routing."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranslationHardnessConfig(BaseModel):
    """Weights and threshold for opt-in hard-page model escalation."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    threshold: float = Field(default=2.0, ge=0.0)
    inline_icon_density_weight: float = Field(default=2.0, ge=0.0)
    cross_reference_density_weight: float = Field(default=2.0, ge=0.0)
    table_presence_weight: float = Field(default=1.0, ge=0.0)
    segment_count_weight: float = Field(default=0.05, ge=0.0)
    segment_length_weight: float = Field(default=0.001, ge=0.0)
