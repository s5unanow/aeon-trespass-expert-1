/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type RunId = string;
export type Info = number;
export type Warning = number;
export type Error = number;
export type Critical = number;
export type Blocking = boolean;
export type RecordRefs = string[];
export type ReviewPackRef = string;

/**
 * Aggregated QA summary for a document.
 */
export interface QASummaryV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  run_id?: RunId;
  counts?: SeverityCounts;
  waived_counts?: SeverityCounts;
  blocking?: Blocking;
  record_refs?: RecordRefs;
  review_pack_ref?: ReviewPackRef;
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
