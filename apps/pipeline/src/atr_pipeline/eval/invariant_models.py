"""Pydantic models for extraction invariant verification results."""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_record_v1 import QARecordV1


class PageVerificationResult(BaseModel):
    """Invariant verification result for a single page."""

    page_id: str
    records: list[QARecordV1] = Field(default_factory=list)
    passed: bool = True


class VerificationReport(BaseModel):
    """Aggregate invariant verification report for a document."""

    document_id: str
    timestamp: str
    pages: list[PageVerificationResult] = Field(default_factory=list)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    blocking: bool = False
    passed: bool = True
