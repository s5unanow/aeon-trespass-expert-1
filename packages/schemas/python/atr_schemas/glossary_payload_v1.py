"""GlossaryPayloadV1 — frontend glossary payload."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GlossaryEntryV1(BaseModel):
    """A single glossary entry for the frontend."""

    concept_id: str
    preferred_term: str
    source_term: str = ""
    aliases: list[str] = Field(default_factory=list)
    icon_binding: str | None = None
    notes: str = ""


class GlossaryPayloadV1(BaseModel):
    """Frontend glossary payload."""

    schema_version: str = Field(default="glossary_payload.v1", pattern=r"^glossary_payload\.v\d+$")
    document_id: str
    entries: list[GlossaryEntryV1] = Field(default_factory=list)
