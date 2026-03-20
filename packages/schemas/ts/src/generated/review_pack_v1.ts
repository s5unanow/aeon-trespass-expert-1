/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type RunId = string;
export type TotalFindings = number;
export type BlockingFindings = number;
export type WaivedFindings = number;
export type SchemaVersion1 = string;
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
export type DocumentId1 = string;
export type PageId = string | null;
export type EntityRef = string | null;
export type Message = string;
export type Available = boolean;
export type Fixer = string;
export type EvidenceRefs = string[];
export type Waived = boolean;
export type WaiverRef = string | null;
export type WaiverId = string;
export type Code1 = string;
export type PageId1 = string | null;
export type Reason = string;
export type ApprovedBy = string;
export type ApprovedAt = string;
export type Findings = ReviewFinding[];

/**
 * Human-reviewable bundle of blocking/ambiguous QA findings.
 *
 * Contains all unwaived blocking findings grouped by page,
 * plus pre-filled waiver templates that a reviewer can approve.
 */
export interface ReviewPackV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  run_id?: RunId;
  total_findings?: TotalFindings;
  blocking_findings?: BlockingFindings;
  waived_findings?: WaivedFindings;
  findings?: Findings;
}
/**
 * A single finding with its waiver template.
 */
export interface ReviewFinding {
  record: QARecordV1;
  waiver_template: WaiverV1;
}
/**
 * A single QA finding.
 */
export interface QARecordV1 {
  schema_version?: SchemaVersion1;
  qa_id: QaId;
  layer: QALayer;
  severity: Severity;
  code: Code;
  document_id?: DocumentId1;
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
/**
 * A single approved QA waiver.
 *
 * Matches findings by rule code and optionally by page.
 */
export interface WaiverV1 {
  waiver_id: WaiverId;
  code: Code1;
  page_id?: PageId1;
  reason: Reason;
  approved_by: ApprovedBy;
  approved_at?: ApprovedAt;
}
