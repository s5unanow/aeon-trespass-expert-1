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
  | 'accessibility';
export type Severity = 'info' | 'warning' | 'error' | 'critical';
export type Code = string;
export type DocumentId = string;
export type PageId = string | null;
export type EntityRef = string | null;
export type Message = string;
export type Available = boolean;
export type Fixer = string;
export type EvidenceRefs = string[];
export type Waived = boolean;
export type WaiverRef = string | null;

/**
 * A single QA finding.
 */
export interface QARecordV1 {
  schema_version?: SchemaVersion;
  qa_id: QaId;
  layer: QALayer;
  severity: Severity;
  code: Code;
  document_id?: DocumentId;
  page_id?: PageId;
  entity_ref?: EntityRef;
  message?: Message;
  expected?: Expected;
  actual?: Actual;
  auto_fix?: AutoFix | null;
  evidence_refs?: EvidenceRefs;
  waived?: Waived;
  waiver_ref?: WaiverRef;
}
export interface Expected {
  [k: string]: unknown;
}
export interface Actual {
  [k: string]: unknown;
}
/**
 * Available auto-fix for a QA issue.
 */
export interface AutoFix {
  available?: Available;
  fixer?: Fixer;
}
