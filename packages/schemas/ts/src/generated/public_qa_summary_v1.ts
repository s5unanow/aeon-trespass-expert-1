/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type Edition = string;
export type Info = number;
export type Warning = number;
export type Error = number;
export type Critical = number;
export type Blocking = boolean;

/**
 * Public-facing QA summary written to ``<edition>/data/qa_summary.json``.
 */
export interface PublicQASummaryV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  edition?: Edition;
  counts?: SeverityCounts;
  waived_counts?: SeverityCounts;
  blocking?: Blocking;
}
/**
 * Counts by severity level.
 */
export interface SeverityCounts {
  info?: Info;
  warning?: Warning;
  error?: Error;
  critical?: Critical;
}
