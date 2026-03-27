"""AssistantCitationV1 — citation reference linking an answer to rulebook evidence."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AssistantCitationV1(BaseModel):
    """Citation tying an assistant answer claim to a specific rule chunk.

    Each citation resolves to a reader deep link and includes a short
    verbatim snippet from the rulebook for verification.
    """

    schema_version: str = Field(
        default="assistant_citation.v1", pattern=r"^assistant_citation\.v\d+$"
    )
    document_id: str
    edition: str
    page_id: str = Field(pattern=r"^p\d{4}$")
    source_page_number: int = Field(ge=1)
    canonical_anchor_id: str
    deep_link: str = ""
    quote_snippet: str = ""
    relevance_reason: str = ""
