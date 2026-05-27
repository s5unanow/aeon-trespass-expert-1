"""TranslationStyleCriticV1 — paragraph-local Russian style critic findings."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from atr_schemas.enums import Severity


class TranslationStyleCriticFindingV1(BaseModel):
    """A single paragraph-local Russian readability/style finding."""

    model_config = ConfigDict(extra="forbid")

    paragraph_id: str = Field(min_length=1)
    severity: Severity
    quote: str = Field(min_length=1)
    why: str = Field(min_length=1)
    suggestions: list[str] = Field(min_length=1)


class TranslationStyleCriticPageV1(BaseModel):
    """Style critic findings for one translated page."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="translation_style_critic.v1",
        pattern=r"^translation_style_critic\.v\d+$",
    )
    document_id: str
    page_id: str
    findings: list[TranslationStyleCriticFindingV1] = Field(default_factory=list)
