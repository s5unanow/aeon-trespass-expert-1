/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
export type Width = number;
export type Height = number;
export type WordId = string;
export type Text = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type FontName = string;
export type FontSize = number;
export type Flags = number;
export type Words = WordEvidence[];
export type SpanId = string;
export type Text1 = string;
export type FontName1 = string;
export type FontSize1 = number;
export type Flags1 = number;
export type Color = number;
export type Spans = SpanEvidence[];
export type ImageId = string;
export type WidthPx = number;
export type HeightPx = number;
export type Colorspace = string;
export type Xref = number;
export type ImageBlocks = ImageBlockEvidence[];

/**
 * Native text and image evidence for a single page.
 */
export interface NativePageV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  dimensions_pt: PageDimensions;
  words?: Words;
  spans?: Spans;
  image_blocks?: ImageBlocks;
  extractor_meta?: ExtractorMeta;
}
/**
 * Source page dimensions in PDF points.
 */
export interface PageDimensions {
  width: Width;
  height: Height;
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
 * A text span with consistent formatting.
 */
export interface SpanEvidence {
  span_id: SpanId;
  text: Text1;
  bbox: Rect;
  font_name?: FontName1;
  font_size?: FontSize1;
  flags?: Flags1;
  color?: Color;
}
/**
 * An image object found in the PDF page.
 */
export interface ImageBlockEvidence {
  image_id: ImageId;
  bbox: Rect;
  width_px?: WidthPx;
  height_px?: HeightPx;
  colorspace?: Colorspace;
  xref?: Xref;
}
export interface ExtractorMeta {
  [k: string]: string;
}
