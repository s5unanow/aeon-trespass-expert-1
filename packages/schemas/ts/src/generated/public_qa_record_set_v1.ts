/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type QaId = string;
export type QALayer =
  | 'extraction'
  | 'structure'
  | 'terminology'
  | 'icon_symbol'
  | 'asset_link'
  | 'render'
  | 'visual'
  | 'accessibility'
  | 'user_feedback'
  | 'confidence';
export type Severity = 'info' | 'warning' | 'error' | 'critical';
export type Code = string;
export type PageId = string | null;
export type EntityRef = string | null;
export type Message = string;
export type Waived = boolean;
export type Records = PublicQARecordV1[];

/**
 * Public-facing QA record list written to ``<edition>/data/qa_records.json``.
 */
export interface PublicQARecordSetV1 {
  schema_version?: SchemaVersion;
  records?: Records;
}
/**
 * Public-facing single QA finding.
 */
export interface PublicQARecordV1 {
  qa_id: QaId;
  layer: QALayer;
  severity: Severity;
  code: Code;
  page_id?: PageId;
  entity_ref?: EntityRef;
  message?: Message;
  waived?: Waived;
}
