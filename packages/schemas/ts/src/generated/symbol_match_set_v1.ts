/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type SymbolId = string;
export type InstanceId = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type Score = number;
export type SourceAssetId = string;
export type Inline = boolean;
export type Matches = SymbolMatch[];
export type UnmatchedCandidates = number;

/**
 * All symbol detections for a single page.
 */
export interface SymbolMatchSetV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  matches?: Matches;
  unmatched_candidates?: UnmatchedCandidates;
}
/**
 * A single detected symbol match on a page.
 */
export interface SymbolMatch {
  symbol_id: SymbolId;
  instance_id?: InstanceId;
  bbox: Rect;
  score: Score;
  source_asset_id?: SourceAssetId;
  inline?: Inline;
}
/**
 * Bounding box in PDF points: [x0, y0, x1, y1].
 */
export interface Rect {
  x0: X0;
  y0: Y0;
  x1: X1;
  y1: Y1;
}
