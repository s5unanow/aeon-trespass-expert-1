/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type PatchId = string;
export type TargetArtifactRef = string;
/**
 * Which artifact schema a patch set targets.
 */
export type PatchTargetKind = 'page_ir' | 'resolved_page' | 'layout_page' | 'page_evidence';
export type Op = string;
export type Path = string;
/**
 * Classification of what a patch operation corrects.
 */
export type PatchScope =
  | 'text'
  | 'block_structure'
  | 'reading_order'
  | 'region_assignment'
  | 'asset_link'
  | 'symbol_resolution'
  | 'confidence_override'
  | 'fallback_resolution';
export type Operations = PatchOperation[];
export type Reason = string;
export type Author = string;
export type Author1 = string;
export type CreatedAt = string | null;
/**
 * Page confidence before patch
 */
export type SourceConfidence = number | null;
/**
 * Expected change in page confidence after patch
 */
export type ExpectedConfidenceDelta = number | null;

/**
 * A set of typed patches for a specific artifact.
 */
export interface PatchSetV1 {
  schema_version?: SchemaVersion;
  patch_id: PatchId;
  target_artifact_ref?: TargetArtifactRef;
  /**
   * Which artifact schema this patch targets
   */
  target_kind?: PatchTargetKind | null;
  operations?: Operations;
  reason?: Reason;
  author?: Author;
  provenance?: PatchProvenance | null;
}
/**
 * A single patch operation.
 */
export interface PatchOperation {
  op: Op;
  path: Path;
  value?: Value;
  /**
   * Classification of what this operation corrects
   */
  scope?: PatchScope | null;
}
export interface Value {
  [k: string]: unknown;
}
/**
 * Tracks who/what created the patch and its expected confidence impact.
 */
export interface PatchProvenance {
  author?: Author1;
  created_at?: CreatedAt;
  source_confidence?: SourceConfidence;
  expected_confidence_delta?: ExpectedConfidenceDelta;
}
