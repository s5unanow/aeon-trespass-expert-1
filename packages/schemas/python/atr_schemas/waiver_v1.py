"""WaiverV1 — typed QA waiver for approved exceptions."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WaiverV1(BaseModel):
    """A single approved QA waiver.

    Matches findings by rule code and optionally by page.
    """

    waiver_id: str
    code: str
    page_id: str | None = None
    reason: str
    approved_by: str
    approved_at: str = ""


class WaiverSetV1(BaseModel):
    """Collection of waivers for a document."""

    schema_version: str = Field(
        default="waiver_set.v1",
        pattern=r"^waiver_set\.v\d+$",
    )
    document_id: str
    waivers: list[WaiverV1] = Field(default_factory=list)
