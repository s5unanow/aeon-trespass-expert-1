/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type SchemaVersion1 = string;
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
export type Classes = AssetClassV1[];
/**
 * Unique per occurrence, e.g. ao.p0042.001
 */
export type OccurrenceId = string;
/**
 * References the parent AssetClassV1.class_id.
 */
export type ClassId1 = string;
export type PageId = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type X01 = number;
export type Y01 = number;
export type X11 = number;
export type Y11 = number;
/**
 * Where an asset occurrence sits relative to its surrounding content.
 */
export type OccurrenceContext =
  | 'inline'
  | 'line_prefix'
  | 'cell_local'
  | 'block_attached'
  | 'decoration'
  | 'region_float';
export type EvidenceIds = string[];
export type Confidence = number;
export type Occurrences = AssetOccurrenceV1[];

/**
 * Document-wide registry mapping asset classes to their page occurrences.
 *
 * Consumers (symbol resolver, figure resolver) query this registry instead
 * of reaching into ad-hoc page-local data.
 */
export interface AssetRegistryV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  classes?: Classes;
  occurrences?: Occurrences;
}
/**
 * A unique visual entity that may appear one or more times across pages.
 *
 * Asset classes are deduplicated by identity: two occurrences with the same
 * ``exact_hash`` collapse to one class.  Fuzzy identity enables
 * near-duplicate grouping without requiring bit-exact matches.
 */
export interface AssetClassV1 {
  schema_version?: SchemaVersion1;
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
/**
 * A single placement of an asset on a page.
 *
 * Each occurrence references its parent :class:`AssetClassV1` via
 * ``class_id`` and the underlying evidence entities via ``evidence_ids``.
 */
export interface AssetOccurrenceV1 {
  occurrence_id: OccurrenceId;
  class_id: ClassId1;
  page_id: PageId;
  bbox: Rect;
  norm_bbox: NormRect;
  context?: OccurrenceContext;
  evidence_ids?: EvidenceIds;
  confidence?: Confidence;
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
/**
 * Bounding box in normalized [0,1] page coordinate space.
 */
export interface NormRect {
  x0: X01;
  y0: Y01;
  x1: X11;
  y1: Y11;
}
