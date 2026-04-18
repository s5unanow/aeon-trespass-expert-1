/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type Edition = string;
export type PageId = string;
/**
 * Coarse classification of reader-submitted page feedback.
 */
export type FeedbackIssueType = 'translation' | 'extraction' | 'rendering' | 'other';
export type Note = string;
export type Url = string;
export type UserAgent = string;
export type Timestamp = string;

/**
 * A single reader feedback submission.
 */
export interface FeedbackSubmissionV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  edition: Edition;
  page_id: PageId;
  issue_type: FeedbackIssueType;
  note?: Note;
  url?: Url;
  user_agent?: UserAgent;
  timestamp: Timestamp;
}
