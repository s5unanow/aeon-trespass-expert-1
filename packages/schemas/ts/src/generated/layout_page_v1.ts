/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type ZoneId = string;
export type Kind = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type Confidence = number;
export type Zones = LayoutZone[];
export type ReadingOrderCandidates = string[][];
export type PageId1 = string;
export type ColumnCount = number;
export type ZoneOverlapRatio = number;
export type NativeTextCoverage = number;
export type ExtractorAgreement = number;
export type HardPage = boolean;
export type RecommendedRoute = string;
export type WordId = string;
export type Text = string;
export type FontName = string;
export type FontSize = number;
export type Flags = number;
/**
 * OCR-derived text evidence populated by the hard-page fallback. Each entry corresponds to a detected text *line* (PaddleOCR emits line-level polygons, not per-word tokens). The field reuses WordEvidence for coordinate/text typing; downstream consumers should treat entries as line-level granularity.
 */
export type OcrWords = WordEvidence[];

/**
 * Secondary layout evidence for a single page.
 */
export interface LayoutPageV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  zones?: Zones;
  reading_order_candidates?: ReadingOrderCandidates;
  difficulty?: DifficultyScoreV1 | null;
  ocr_words?: OcrWords;
}
/**
 * A detected layout zone on a page.
 */
export interface LayoutZone {
  zone_id: ZoneId;
  kind?: Kind;
  bbox: Rect;
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
 * Per-page difficulty classification.
 */
export interface DifficultyScoreV1 {
  page_id: PageId1;
  column_count?: ColumnCount;
  zone_overlap_ratio?: ZoneOverlapRatio;
  native_text_coverage?: NativeTextCoverage;
  extractor_agreement?: ExtractorAgreement;
  hard_page?: HardPage;
  recommended_route?: RecommendedRoute;
}
/**
 * A single word extracted from the PDF.
 */
export interface WordEvidence {
  word_id: WordId;
  text: Text;
  bbox: Rect;
  font_name?: FontName;
  font_size?: FontSize;
  flags?: Flags;
}
