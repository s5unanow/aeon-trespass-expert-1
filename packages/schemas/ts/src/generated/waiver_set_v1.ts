/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type WaiverId = string;
export type Code = string;
export type PageId = string | null;
export type Reason = string;
export type ApprovedBy = string;
export type ApprovedAt = string;
export type Waivers = WaiverV1[];

/**
 * Collection of waivers for a document.
 */
export interface WaiverSetV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  waivers?: Waivers;
}
/**
 * A single approved QA waiver.
 *
 * Matches findings by rule code and optionally by page.
 */
export interface WaiverV1 {
  waiver_id: WaiverId;
  code: Code;
  page_id?: PageId;
  reason: Reason;
  approved_by: ApprovedBy;
  approved_at?: ApprovedAt;
}
