/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type RunId = string;
export type Edition = string;
export type Timestamp = string;
export type PagesTotal = number;
export type PagesWithFindings = number;
export type CleanPageRate = number;
export type Info = number;
export type Warning = number;
export type Error = number;
export type Critical = number;
export type Code = string;
export type Count = number;
export type FindingsByCodeTop10 = FindingCodeCount[];
export type WaivedCount = number;
export type BlockingCount = number;
export type AvgFindingsPerPage = number;

/**
 * Per-run QA metrics artifact.
 *
 * All distribution fields (by-severity / by-layer / by-code) reflect
 * **active** (non-waived) records only. Waived records are tallied
 * separately in ``waived_count`` so health reporting isn't inflated by
 * intentionally-suppressed findings.
 */
export interface QAMetricsV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  run_id?: RunId;
  edition?: Edition;
  timestamp?: Timestamp;
  pages_total?: PagesTotal;
  pages_with_findings?: PagesWithFindings;
  clean_page_rate?: CleanPageRate;
  findings_by_severity?: SeverityCounts;
  findings_by_layer?: FindingsByLayer;
  findings_by_code_top10?: FindingsByCodeTop10;
  waived_count?: WaivedCount;
  blocking_count?: BlockingCount;
  avg_findings_per_page?: AvgFindingsPerPage;
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
export interface FindingsByLayer {
  [k: string]: number;
}
/**
 * Count of QA findings grouped by rule code.
 */
export interface FindingCodeCount {
  code: Code;
  count?: Count;
}
