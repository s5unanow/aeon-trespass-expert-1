"""ConceptRegistryV1 — glossary concepts and terminology rules."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConceptSource(BaseModel):
    """English source form of a concept."""

    lang: str = "en"
    lemma: str
    aliases: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)


class ConceptTarget(BaseModel):
    """Russian target form of a concept."""

    lang: str = "ru"
    lemma: str
    allowed_surface_forms: list[str] = Field(default_factory=list)


class PhraseTemplate(BaseModel):
    """High-priority multiword translation mapping."""

    source_pattern: str
    target_pattern: str


class ValidationPolicy(BaseModel):
    """Severity policy for concept enforcement."""

    missing: str = "error"
    forbidden: str = "error"
    non_preferred_allowed: str = "warning"


class ConceptV1(BaseModel):
    """A single glossary/terminology concept."""

    concept_id: str
    kind: str = "term"  # term, phrase, icon_term, entity, mechanic
    version: str = ""
    source: ConceptSource
    target: ConceptTarget
    icon_binding: str | None = None
    phrase_templates: list[PhraseTemplate] = Field(default_factory=list)
    forbidden_targets: list[str] = Field(default_factory=list)
    validation_policy: ValidationPolicy = Field(default_factory=ValidationPolicy)
    notes: str = ""


class ConceptRegistryV1(BaseModel):
    """Full concept registry for a document."""

    schema_version: str = Field(
        default="concept_registry.v1", pattern=r"^concept_registry\.v\d+$"
    )
    version: str = ""
    concepts: list[ConceptV1] = Field(default_factory=list)
