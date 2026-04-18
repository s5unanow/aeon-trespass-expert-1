"""FeedbackSubmissionV1 — reader-submitted page feedback blob.

Contract between the web reader ("Report issue" button) and the pipeline's
``scripts/ingest_user_feedback.py`` ingest script. Each submission is
turned into a ``QARecordV1`` with ``layer=user_feedback`` and
``severity=info``.

Every field is attacker-controllable (readers drop arbitrary JSON into
``artifacts/feedback/``), and several fields are later concatenated into
filesystem paths. So inputs are validated **at the trust boundary** with
strict regexes, length caps, and an ISO-8601 parse check on ``timestamp``.

Keep this model small and stable; it is the only shared shape between the
reader and the ingest path, and changes here force both sides to update.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from atr_schemas.enums import FeedbackIssueType


class FeedbackSubmissionV1(BaseModel):
    """A single reader feedback submission."""

    schema_version: str = Field(
        default="user_feedback.v1",
        pattern=r"^user_feedback\.v\d+$",
    )
    # document_id follows the existing convention for configs/documents/*.toml
    # entries (e.g. "ato_core_v1_1"): lowercase ascii, digits, underscores.
    document_id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=64)
    # Two-letter language code (e.g. "ru", "en"). Must match the edition
    # keys actually shipped by the site bundle.
    edition: str = Field(pattern=r"^[a-z]{2}$")
    # Canonical page identifier used across the rest of the schema set —
    # a lowercase "p" followed by exactly four digits (e.g. "p0042").
    page_id: str = Field(pattern=r"^p\d{4}$")
    issue_type: FeedbackIssueType
    note: str = Field(default="", max_length=4000)
    url: str = Field(default="", max_length=2048)
    user_agent: str = Field(default="", max_length=512)
    # Kept as a string (the web reader sends ``Date.toISOString()``) but the
    # field validator below rejects anything Python's ``fromisoformat``
    # cannot parse, and also rejects path separators defensively.
    timestamp: str = Field(max_length=64)

    @field_validator("timestamp")
    @classmethod
    def _timestamp_is_iso8601(cls, value: str) -> str:
        # Defence in depth: the timestamp gets substituted into a filename
        # component downstream, so forbid separators even before we look at
        # parseability.
        for bad in ("/", "\\", ".."):
            if bad in value:
                raise ValueError(f"timestamp must not contain {bad!r}")
        try:
            # datetime.fromisoformat accepts the trailing "Z" suffix from
            # Python 3.11 onwards, matching what toISOString() emits.
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"timestamp is not a valid ISO-8601 datetime: {value!r}") from exc
        return value
