"""SearchDocsV1 — search document artifacts for the frontend."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchDocEntry(BaseModel):
    """A single searchable document entry."""

    page_id: str
    title: str = ""
    text: str = ""
    normalized_terms: list[str] = Field(default_factory=list)
    section_path: list[str] = Field(default_factory=list)
    source_page_number: int = 0


class SearchDocsV1(BaseModel):
    """Collection of search documents for a document edition."""

    schema_version: str = Field(default="search_docs.v1", pattern=r"^search_docs\.v\d+$")
    document_id: str
    docs: list[SearchDocEntry] = Field(default_factory=list)
