// Reader feedback submission shape.
//
// Kept deliberately small and stable: the pipeline-side ingest script
// (scripts/ingest_user_feedback.py) reads this exact structure and turns
// each blob into a QARecordV1 with layer=user_feedback, severity=info.
//
// When changing these fields, update the ingest script and its tests.

export type FeedbackIssueType = 'translation' | 'extraction' | 'rendering' | 'other';

export const FEEDBACK_SCHEMA_VERSION = 'user_feedback.v1' as const;

export interface FeedbackSubmission {
  schema_version: typeof FEEDBACK_SCHEMA_VERSION;
  document_id: string;
  edition: string;
  page_id: string;
  issue_type: FeedbackIssueType;
  note: string;
  url: string;
  user_agent: string;
  timestamp: string; // ISO-8601
}

export function buildFeedbackFilename(submission: FeedbackSubmission): string {
  const safeTs = submission.timestamp.replace(/[:.]/g, '-');
  return `feedback-${submission.document_id}-${submission.edition}-${submission.page_id}-${safeTs}.json`;
}
