"""Hard-page routing config for the translation stage (S5U-1542).

Kept in its own module so ``config/models.py`` stays under the 400-line ceiling.
Re-exported from ``config.models`` for backward-compatible imports.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TranslationHardnessConfig(BaseModel):
    """Per-page hardness routing for the translation stage (S5U-1542).

    When ``enabled`` is False (the default), the translation stage sends every
    batch to ``TranslationConfig.model_default`` exactly as before — turning
    this section on is the only thing that changes routing behaviour, so
    existing configs stay byte-identical.

    When enabled, each page's ``TranslationBatchV1`` is scored by a
    deterministic linear model over four signals available before translation:
    inline icon density, cross-reference density, table-block presence, and
    segment count. A page whose weighted score is ``>= threshold`` is routed to
    ``TranslationConfig.model_hard``; every other page keeps ``model_default``.

    All knobs are non-negative. ``extra="forbid"`` means a typo in the TOML
    (``wieght_icon_density``) fails config load rather than being silently
    dropped.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    threshold: float = Field(default=2.0, ge=0.0)
    weight_icon_density: float = Field(default=1.0, ge=0.0)
    weight_xref_density: float = Field(default=1.0, ge=0.0)
    weight_table_ratio: float = Field(default=1.0, ge=0.0)
    weight_segment_load: float = Field(default=0.05, ge=0.0)
