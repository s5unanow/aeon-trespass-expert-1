"""FeedbackSubmissionV1 — reader-submitted page feedback blob.

Contract between the web reader ("Report issue" button) and the pipeline's
``scripts/ingest_user_feedback.py`` ingest script. Each submission is
turned into a ``QARecordV1`` with ``layer=user_feedback`` and
``severity=info``.

Keep this model small and stable; it is the only shared shape between the
reader and the ingest path, and changes here force both sides to update.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from atr_schemas.enums import FeedbackIssueType


class FeedbackSubmissionV1(BaseModel):
    """A single reader feedback submission."""

    schema_version: str = Field(
        default="user_feedback.v1",
        pattern=r"^user_feedback\.v\d+$",
    )
    document_id: str
    edition: str
    page_id: str
    issue_type: FeedbackIssueType
    note: str = ""
    url: str = ""
    user_agent: str = ""
    timestamp: str
