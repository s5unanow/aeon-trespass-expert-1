// Reader feedback submission shape.
//
// The canonical contract lives in Pydantic
// (`packages/schemas/python/atr_schemas/feedback_submission_v1.py`) and the
// TypeScript types are generated from the JSON Schema (see `make codegen`).
// The pipeline-side ingest script (`scripts/ingest_user_feedback.py`)
// consumes the same model, so both sides are kept in sync automatically.
//
// This module only holds the filename helper and the schema-version literal
// used by the web reader to produce a blob the ingest script accepts.

import type { feedbackSubmissionV1, FeedbackSubmissionV1 } from '@atr/schemas';

export type FeedbackSubmission = FeedbackSubmissionV1;
export type FeedbackIssueType = feedbackSubmissionV1.FeedbackIssueType;

export const FEEDBACK_SCHEMA_VERSION = 'user_feedback.v1' as const;

export function buildFeedbackFilename(submission: FeedbackSubmission): string {
  const safeTs = submission.timestamp.replace(/[:.]/g, '-');
  return `feedback-${submission.document_id}-${submission.edition}-${submission.page_id}-${safeTs}.json`;
}
