"""NavPayloadV1 — document navigation payload for the frontend."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NavEntryV1(BaseModel):
    """A single page entry in the navigation payload."""

    page_id: str
    title: str = ""
    source_page_number: int = 0
    prev: str | None = None
    next: str | None = None


class NavPayloadV1(BaseModel):
    """Frontend navigation payload — ordered page list with prev/next links."""

    schema_version: str = Field(default="nav_payload.v1", pattern=r"^nav_payload\.v\d+$")
    document_id: str
    pages: list[NavEntryV1] = Field(default_factory=list)
