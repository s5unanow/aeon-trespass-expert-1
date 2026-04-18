#!/usr/bin/env python3
"""Convert reader-submitted feedback blobs into QARecordV1 entries.

Flow
----
1. A reader clicks "Report issue" in the web reader and downloads a JSON
   blob shaped like ``FeedbackSubmissionV1`` (see
   ``apps/web/src/lib/feedback/schema.ts``).
2. The reviewer commits (or drops) that blob into ``artifacts/feedback/``.
3. This script reads each blob and persists a ``UserFeedbackRecordSetV1``
   (one set per (document, edition, page)) into the shared
   ``ArtifactStore`` so the QA stage, review-pack, waiver loader, and
   ``export_to_web`` automatically surface the records alongside
   rule-derived findings.

The ``user_feedback`` layer is intentionally non-blocking: every record
uses ``severity=info`` so the publish gate is unaffected while triage can
still see feedback via ``qa_records.json`` and the dashboard.

Usage
-----
    uv run python scripts/ingest_user_feedback.py \\
        --feedback-dir artifacts/feedback \\
        --document-id ato_core_v1_1

The artifact root for the document is resolved from
``configs/documents/<doc_id>.toml`` via ``load_document_config``. Re-running
with the same inputs is idempotent: the store is content-addressed.

Fixes
-----
* S5U-605: records now go through ``ArtifactStore`` so downstream QA
  surfaces can see them (previously written to an orphan flat directory).
* S5U-602: replaced ``print`` with ``logging`` (matching the pipeline's
  actual convention) and replaced raw ``write_text`` with
  ``ArtifactStore.put_json`` which uses atomic temp-file + rename.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from atr_pipeline.config import load_document_config
from atr_pipeline.stages.qa.user_feedback import persist_submissions
from atr_pipeline.store.artifact_store import ArtifactStore
from atr_schemas.feedback_submission_v1 import FeedbackSubmissionV1

# Keep the historical name exported so existing imports (and tests) continue
# to resolve. The canonical contract lives in ``atr_schemas``.
FeedbackSubmission = FeedbackSubmissionV1

# Matches the logging pattern used by the rest of the pipeline
# (e.g. ``atr_pipeline.cli.commands.run``); structlog isn't a runtime
# dependency of this repo despite the rule mention. Diagnostic messages are
# structured via keyword args so a downstream handler can reformat them.
logger = logging.getLogger("atr_pipeline.ingest_user_feedback")


def _load_submission(path: Path) -> FeedbackSubmissionV1:
    data: Any = json.loads(path.read_text())
    return FeedbackSubmissionV1.model_validate(data)


def ingest_directory(
    feedback_dir: Path,
    store: ArtifactStore,
) -> list[tuple[str, str, str]]:
    """Read every ``*.json`` under *feedback_dir* into the artifact store.

    Returns the list of ``(document_id, edition, page_id)`` tuples that were
    written. Invalid inputs are logged and skipped.
    """
    submissions: list[tuple[FeedbackSubmissionV1, str]] = []
    for src in sorted(feedback_dir.glob("*.json")):
        try:
            submission = _load_submission(src)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning("SKIP %s: invalid submission (%s)", src.name, exc)
            continue
        submissions.append((submission, src.name))

    if not submissions:
        return []
    return persist_submissions(store=store, submissions=submissions)


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
        "--document-id",
        type=str,
        default="ato_core_v1_1",
        help="Document id whose ArtifactStore the records are persisted into.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.feedback_dir.exists():
        logger.warning("feedback-dir does not exist: %s", args.feedback_dir)
        return 0

    config = load_document_config(args.document_id)
    store = ArtifactStore(config.artifact_root)

    written = ingest_directory(args.feedback_dir, store)
    logger.info(
        "Wrote %d user-feedback record set(s) for %s via %s",
        len(written),
        args.document_id,
        config.artifact_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
