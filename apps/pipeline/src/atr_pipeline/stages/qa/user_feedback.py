"""User-feedback ingest + loader helpers.

Reader-submitted feedback flows through the standard ``ArtifactStore`` so the
QA stage, review-pack builder, waiver loader, and ``export_to_web`` all see it
alongside rule-derived and translation-validator findings.

Pattern mirrors ``TranslationQARecordSetV1`` (S5U-596):
    schema_family = f"user_feedback_record_set.v1.{edition}"
    scope         = "page"
    entity_id     = page_id

The edition suffix matches the ``page_ir.v1.<edition>`` convention so the
per-edition QA run only picks up records for its own edition.
"""

from __future__ import annotations

from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.enums import QALayer, Severity
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1
from atr_schemas.qa_record_v1 import QARecordV1
from atr_schemas.user_feedback_record_set_v1 import UserFeedbackRecordSetV1


def schema_family_for(edition: str) -> str:
    """Schema family used to store the per-edition record set."""
    return f"user_feedback_record_set.v1.{edition}"


def feedback_to_qa_record(submission: FeedbackSubmissionV1, source_file: str) -> QARecordV1:
    """Convert a reader feedback submission into a ``QARecordV1`` (info-level)."""
    qa_id = build_qa_id(submission)
    message_parts = [f"Reader feedback ({submission.issue_type})"]
    if submission.note:
        message_parts.append(submission.note)
    message = ": ".join(message_parts)
    return QARecordV1(
        qa_id=qa_id,
        layer=QALayer.USER_FEEDBACK,
        severity=Severity.INFO,
        code=f"USER_FEEDBACK_{submission.issue_type.upper()}",
        document_id=submission.document_id,
        page_id=submission.page_id,
        entity_ref=None,
        message=message,
        expected=None,
        actual={
            "issue_type": submission.issue_type,
            "note": submission.note,
            "edition": submission.edition,
            "url": submission.url,
            "user_agent": submission.user_agent,
            "timestamp": submission.timestamp,
            "source_file": source_file,
        },
    )


def build_qa_id(submission: FeedbackSubmissionV1) -> str:
    """Stable identifier so re-ingesting the same blob is idempotent."""
    safe_ts = submission.timestamp.replace(":", "-").replace(".", "-")
    return f"qa.{submission.page_id}.user_feedback.{safe_ts}"


def persist_submissions(
    *,
    store: ArtifactStore,
    submissions: list[tuple[FeedbackSubmissionV1, str]],
) -> list[tuple[str, str, str]]:
    """Group submissions by (document_id, edition, page_id) and persist.

    Each group is serialised into a single ``UserFeedbackRecordSetV1`` and
    written via ``ArtifactStore.put_json``. Returns a list of
    ``(document_id, edition, page_id)`` tuples for every group written.
    """
    groups: dict[tuple[str, str, str], list[QARecordV1]] = {}
    for submission, source_file in submissions:
        key = (submission.document_id, submission.edition, submission.page_id)
        record = feedback_to_qa_record(submission, source_file=source_file)
        groups.setdefault(key, []).append(record)

    written: list[tuple[str, str, str]] = []
    for (document_id, edition, page_id), records in groups.items():
        record_set = UserFeedbackRecordSetV1(
            document_id=document_id,
            edition=edition,
            page_id=page_id,
            records=records,
        )
        store.put_json(
            document_id=document_id,
            schema_family=schema_family_for(edition),
            scope="page",
            entity_id=page_id,
            data=record_set,
        )
        written.append((document_id, edition, page_id))
    return written


def load_user_feedback_records(
    *,
    store: ArtifactStore,
    document_id: str,
    edition: str,
    page_id: str,
) -> list[QARecordV1]:
    """Load any persisted user-feedback records for a (page, edition)."""
    data = store.load_latest_json(
        document_id=document_id,
        schema_family=schema_family_for(edition),
        scope="page",
        entity_id=page_id,
    )
    if not data:
        return []
    record_set = UserFeedbackRecordSetV1.model_validate(data)
    return list(record_set.records)
