/* Auto-generated from JSON Schema — do not edit */

/**
 * Unique per occurrence, e.g. ao.p0042.001
 */
export type OccurrenceId = string;
/**
 * References the parent AssetClassV1.class_id.
 */
export type ClassId = string;
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

/**
 * A single placement of an asset on a page.
 *
 * Each occurrence references its parent :class:`AssetClassV1` via
 * ``class_id`` and the underlying evidence entities via ``evidence_ids``.
 */
export interface AssetOccurrenceV1 {
  occurrence_id: OccurrenceId;
  class_id: ClassId;
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
