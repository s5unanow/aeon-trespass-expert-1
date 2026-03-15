/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type BatchId = string;
export type SegmentId = string;
export type Type = 'text';
export type Text = string;
export type Marks = string[];
export type LanguageCode = 'en' | 'ru';
export type SourceWordIds = string[];
export type Type1 = 'icon';
export type SymbolId = string;
export type InstanceId = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type SourceAssetId = string;
export type Type2 = 'figure_ref';
export type AssetId = string;
export type Label = string;
export type Type3 = 'xref';
export type TargetPageId = string;
export type TargetSectionId = string;
export type Label1 = string;
export type Type4 = 'line_break';
export type Type5 = 'term_mark';
export type ConceptId = string;
export type SurfaceForm = string;
export type TargetInline = (
  | TextInline
  | IconInline
  | FigureRefInline
  | XrefInline
  | LineBreakInline
  | TermMarkInline
)[];
export type ConceptId1 = string;
export type SurfaceForm1 = string;
export type ConceptRealizations = ConceptRealization[];
export type Segments = TranslatedSegment[];

/**
 * Structured translation response.
 */
export interface TranslationResultV1 {
  schema_version?: SchemaVersion;
  batch_id: BatchId;
  segments?: Segments;
}
/**
 * A single translated block.
 */
export interface TranslatedSegment {
  segment_id: SegmentId;
  target_inline?: TargetInline;
  concept_realizations?: ConceptRealizations;
}
/**
 * Plain text inline node.
 */
export interface TextInline {
  type?: Type;
  text: Text;
  marks?: Marks;
  lang?: LanguageCode | null;
  source_word_ids?: SourceWordIds;
}
/**
 * Inline icon node, recovered from symbol catalog matching.
 */
export interface IconInline {
  type?: Type1;
  symbol_id: SymbolId;
  instance_id?: InstanceId;
  bbox?: Rect | null;
  display_hint?: DisplayHint;
  source_asset_id?: SourceAssetId;
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
export interface DisplayHint {
  [k: string]: number | boolean;
}
/**
 * Inline reference to a figure asset.
 */
export interface FigureRefInline {
  type?: Type2;
  asset_id: AssetId;
  label?: Label;
}
/**
 * Cross-reference to another page or section.
 */
export interface XrefInline {
  type?: Type3;
  target_page_id?: TargetPageId;
  target_section_id?: TargetSectionId;
  label?: Label1;
}
/**
 * Explicit line break.
 */
export interface LineBreakInline {
  type?: Type4;
}
/**
 * Glossary term marker.
 */
export interface TermMarkInline {
  type?: Type5;
  concept_id: ConceptId;
  surface_form?: SurfaceForm;
}
/**
 * How a concept was realized in the target language.
 */
export interface ConceptRealization {
  concept_id: ConceptId1;
  surface_form: SurfaceForm1;
}
