/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
export type SourceNativeHash = string;
export type SourceLayoutHash = string;
export type Extractor = string;
export type ExtractorVersion = string;
export type ExtractionTimestamp = string;
/**
 * Base coordinate system
 */
export type CoordinateSpace = string;
export type Width = number;
export type Height = number;
export type Kind = 'char';
export type EvidenceId = string;
export type Text = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type X01 = number;
export type Y01 = number;
export type X11 = number;
export type Y11 = number;
export type FontName = string;
export type FontSize = number;
export type Flags = number;
export type Color = number;
export type Kind1 = 'line';
export type EvidenceId1 = string;
export type Text1 = string;
export type CharIds = string[];
export type WritingDirection = string;
export type Kind2 = 'text_span';
export type EvidenceId2 = string;
export type Text2 = string;
export type FontName1 = string;
export type FontSize1 = number;
export type Flags1 = number;
export type Color1 = number;
export type CharIds1 = string[];
export type Kind3 = 'image_occurrence';
export type EvidenceId3 = string;
export type WidthPx = number;
export type HeightPx = number;
export type Colorspace = string;
export type Xref = number;
export type ImageHash = string;
export type Kind4 = 'vector_path';
export type EvidenceId4 = string;
export type PathOps = string[];
export type StrokeColor = number | null;
export type FillColor = number | null;
export type LineWidth = number;
export type Kind5 = 'vector_cluster';
export type EvidenceId5 = string;
export type PathIds = string[];
export type ClusterHash = string;
export type Kind6 = 'table_candidate';
export type EvidenceId6 = string;
export type RowCount = number;
export type ColCount = number;
export type CellEvidenceIds = string[];
export type Confidence = number;
export type Kind7 = 'region_candidate';
export type EvidenceId7 = string;
/**
 * Semantic region classification.
 */
export type RegionKind =
  | 'body'
  | 'sidebar'
  | 'header'
  | 'footer'
  | 'figure_area'
  | 'table_area'
  | 'callout_area'
  | 'margin_note'
  | 'full_width'
  | 'unknown';
export type Confidence1 = number;
export type SourceZoneId = string;
export type Entities = (
  | EvidenceChar
  | EvidenceLine
  | EvidenceTextSpan
  | EvidenceImageOccurrence
  | EvidenceVectorPath
  | EvidenceVectorCluster
  | EvidenceTableCandidate
  | EvidenceRegionCandidate
)[];

/**
 * Raw page evidence — all observed entities without semantic interpretation.
 */
export interface PageEvidenceV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  transform: EvidenceTransformMeta;
  entities?: Entities;
}
/**
 * Provenance and transform metadata for the evidence layer.
 */
export interface EvidenceTransformMeta {
  source_native_hash?: SourceNativeHash;
  source_layout_hash?: SourceLayoutHash;
  extractor?: Extractor;
  extractor_version?: ExtractorVersion;
  extraction_timestamp?: ExtractionTimestamp;
  coordinate_space?: CoordinateSpace;
  page_dimensions_pt: PageDimensions;
}
/**
 * Source page dimensions in PDF points.
 */
export interface PageDimensions {
  width: Width;
  height: Height;
}
/**
 * A single character glyph extracted from the PDF.
 */
export interface EvidenceChar {
  kind?: Kind;
  evidence_id: EvidenceId;
  text: Text;
  bbox: Rect;
  norm_bbox: NormRect;
  font_name?: FontName;
  font_size?: FontSize;
  flags?: Flags;
  color?: Color;
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
/**
 * A line of text (sequence of characters).
 */
export interface EvidenceLine {
  kind?: Kind1;
  evidence_id: EvidenceId1;
  text: Text1;
  bbox: Rect;
  norm_bbox: NormRect;
  char_ids?: CharIds;
  writing_direction?: WritingDirection;
}
/**
 * A formatting-consistent text span.
 */
export interface EvidenceTextSpan {
  kind?: Kind2;
  evidence_id: EvidenceId2;
  text: Text2;
  bbox: Rect;
  norm_bbox: NormRect;
  font_name?: FontName1;
  font_size?: FontSize1;
  flags?: Flags1;
  color?: Color1;
  char_ids?: CharIds1;
}
/**
 * An image placed on the page.
 */
export interface EvidenceImageOccurrence {
  kind?: Kind3;
  evidence_id: EvidenceId3;
  bbox: Rect;
  norm_bbox: NormRect;
  width_px?: WidthPx;
  height_px?: HeightPx;
  colorspace?: Colorspace;
  xref?: Xref;
  image_hash?: ImageHash;
}
/**
 * A single vector drawing path.
 */
export interface EvidenceVectorPath {
  kind?: Kind4;
  evidence_id: EvidenceId4;
  bbox: Rect;
  norm_bbox: NormRect;
  path_ops?: PathOps;
  stroke_color?: StrokeColor;
  fill_color?: FillColor;
  line_width?: LineWidth;
}
/**
 * A cluster of related vector paths.
 */
export interface EvidenceVectorCluster {
  kind?: Kind5;
  evidence_id: EvidenceId5;
  bbox: Rect;
  norm_bbox: NormRect;
  path_ids?: PathIds;
  cluster_hash?: ClusterHash;
}
/**
 * A detected table-like structure.
 */
export interface EvidenceTableCandidate {
  kind?: Kind6;
  evidence_id: EvidenceId6;
  bbox: Rect;
  norm_bbox: NormRect;
  row_count?: RowCount;
  col_count?: ColCount;
  cell_evidence_ids?: CellEvidenceIds;
  confidence?: Confidence;
}
/**
 * A spatial region detected from layout analysis.
 */
export interface EvidenceRegionCandidate {
  kind?: Kind7;
  evidence_id: EvidenceId7;
  bbox: Rect;
  norm_bbox: NormRect;
  region_kind?: RegionKind;
  confidence?: Confidence1;
  source_zone_id?: SourceZoneId;
}
