/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
/**
 * Stable identifier, e.g. ac.raster.deadbeef1234
 */
export type ClassId = string;
/**
 * How the asset was originally captured.
 */
export type AssetSourceKind = 'embedded_raster' | 'vector_cluster' | 'rendered_crop';
/**
 * Content hash for exact identity (SHA-256 prefix for rasters, cluster hash for vectors).
 */
export type ExactHash = string;
/**
 * Perceptual hash for near-duplicate matching.
 */
export type FuzzyHash = string;
/**
 * Canonical descriptor for vector-origin assets.
 */
export type VectorSignature = string;
export type WidthPx = number;
export type HeightPx = number;
/**
 * Human-readable label (e.g. symbol name from catalog).
 */
export type Label = string;
/**
 * Evidence ID of the first occurrence that introduced this class.
 */
export type CanonicalEvidenceId = string;

/**
 * A unique visual entity that may appear one or more times across pages.
 *
 * Asset classes are deduplicated by identity: two occurrences with the same
 * ``exact_hash`` collapse to one class.  Fuzzy identity enables
 * near-duplicate grouping without requiring bit-exact matches.
 */
export interface AssetClassV1 {
  schema_version?: SchemaVersion;
  class_id: ClassId;
  source_kind: AssetSourceKind;
  identity?: AssetIdentity;
  width_px?: WidthPx;
  height_px?: HeightPx;
  label?: Label;
  canonical_evidence_id?: CanonicalEvidenceId;
}
/**
 * Identity fingerprints for exact and fuzzy matching.
 */
export interface AssetIdentity {
  exact_hash?: ExactHash;
  fuzzy_hash?: FuzzyHash;
  vector_signature?: VectorSignature;
}
