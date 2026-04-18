"""UserFeedbackRecordSetV1 — per-page reader-feedback QA findings.

Reader-submitted feedback blobs (``FeedbackSubmissionV1``) are converted into
``QARecordV1`` entries with ``layer=user_feedback`` and persisted alongside
other page artifacts so the unified QA stage / review-pack / export pipeline
surfaces them. Edition is part of the artifact's ``schema_family`` suffix
(``user_feedback_record_set.v1.en`` / ``user_feedback_record_set.v1.ru``),
mirroring ``page_ir.v1.<edition>`` so per-edition QA runs load only their
edition's feedback.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.qa_record_v1 import QARecordV1


class UserFeedbackRecordSetV1(BaseModel):
    """A collection of user-feedback QA records for a single (page, edition)."""

    schema_version: str = Field(
        default="user_feedback_record_set.v1",
        pattern=r"^user_feedback_record_set\.v\d+$",
    )
    document_id: str
    edition: str = Field(pattern=r"^[a-z]{2}$")
    page_id: str = Field(pattern=r"^p\d{4}$")
    records: list[QARecordV1] = Field(default_factory=list)
