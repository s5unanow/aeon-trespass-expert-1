"""TranslationQARecordSetV1 — per-page translation QA findings.

The translation stage emits QA findings while validating translated segments
against the source batch. These findings are persisted alongside other page
artifacts so the downstream QA stage can merge them into the unified
``QASummaryV1`` / ``ReviewPackV1`` stream.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_record_v1 import QARecordV1


class TranslationQARecordSetV1(BaseModel):
    """A collection of translation QA records for a single page."""

    schema_version: str = Field(
        default="translation_qa_record_set.v1",
        pattern=r"^translation_qa_record_set\.v\d+$",
    )
    document_id: str
    page_id: str
    records: list[QARecordV1] = Field(default_factory=list)
