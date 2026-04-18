#!/usr/bin/env python3
"""Convert reader-submitted feedback blobs into QARecordV1 entries.

Flow
----
1. A reader clicks "Report issue" in the web reader and downloads a JSON
   blob shaped like ``FeedbackSubmission`` (see
   ``apps/web/src/lib/feedback/schema.ts``).
2. The reviewer commits (or drops) that blob into ``artifacts/feedback/``.
3. This script reads each blob and emits a ``QARecordV1`` with
   ``layer=user_feedback`` and ``severity=info`` into the QA record artifact
   store so the existing review-pack + QA dashboard flow surfaces it.

The ``user_feedback`` layer is intentionally non-blocking: it surfaces for
human triage alongside machine-generated QA findings without affecting the
publish gate.

Usage
-----
    uv run python scripts/ingest_user_feedback.py \\
        --feedback-dir artifacts/feedback \\
        --output-dir artifacts/qa_records

Both directories are created if missing. Each input file produces exactly
one output file; re-running with the same inputs is idempotent (files are
overwritten in place based on their stable ``qa_id``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from atr_schemas.enums import QALayer, Severity
from atr_schemas.qa_record_v1 import QARecordV1


class FeedbackSubmission(BaseModel):
    """Contract between the web reader and this ingest script.

    Mirrors ``FeedbackSubmission`` in
    ``apps/web/src/lib/feedback/schema.ts``. When adding fields, update both
    sides and the component test.
    """

    schema_version: str = Field(default="user_feedback.v1")
    document_id: str
    edition: str
    page_id: str
    issue_type: str
    note: str = ""
    url: str = ""
    user_agent: str = ""
    timestamp: str


def feedback_to_qa_record(submission: FeedbackSubmission, source_file: str) -> QARecordV1:
    """Build a ``QARecordV1`` from a reader feedback submission."""
    qa_id = _build_qa_id(submission)
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


def _build_qa_id(submission: FeedbackSubmission) -> str:
    """Stable identifier so re-ingesting the same blob is idempotent."""
    safe_ts = submission.timestamp.replace(":", "-").replace(".", "-")
    return f"qa.{submission.page_id}.user_feedback.{safe_ts}"


def _load_submission(path: Path) -> FeedbackSubmission:
    data: Any = json.loads(path.read_text())
    return FeedbackSubmission.model_validate(data)


def ingest_directory(feedback_dir: Path, output_dir: Path) -> list[Path]:
    """Read every ``*.json`` under *feedback_dir*, emit QA records to *output_dir*.

    Returns the list of written output paths. Invalid inputs are skipped
    with an error printed to stderr; the caller decides whether to fail the
    overall run.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for src in sorted(feedback_dir.glob("*.json")):
        try:
            submission = _load_submission(src)
        except (ValidationError, json.JSONDecodeError) as exc:
            print(f"SKIP {src.name}: {exc}", file=sys.stderr)
            continue
        record = feedback_to_qa_record(submission, source_file=src.name)
        out_path = output_dir / f"{record.qa_id}.json"
        out_path.write_text(record.model_dump_json(indent=2))
        written.append(out_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--feedback-dir",
        type=Path,
        default=Path("artifacts/feedback"),
        help="Directory containing reader feedback JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/qa_records/user_feedback"),
        help="Where to write the generated QARecordV1 JSON files.",
    )
    args = parser.parse_args(argv)

    if not args.feedback_dir.exists():
        print(f"feedback-dir does not exist: {args.feedback_dir}", file=sys.stderr)
        return 0
    written = ingest_directory(args.feedback_dir, args.output_dir)
    print(f"Wrote {len(written)} QA record(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
