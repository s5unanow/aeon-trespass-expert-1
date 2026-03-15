/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type BatchId = string;
export type SourceLang = string;
export type TargetLang = string;
export type PromptProfile = string;
export type SegmentId = string;
export type BlockType = string;
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
export type SourceInline = (
  | TextInline
  | IconInline
  | FigureRefInline
  | XrefInline
  | LineBreakInline
  | TermMarkInline
)[];
export type PageId = string;
export type SectionPath = string[];
export type PrevHeading = string;
export type RequiredConcepts = string[];
export type ForbiddenTargets = string[];
export type LockedNodes = string[];
export type SourceChecksum = string;
export type Segments = TranslationSegment[];

/**
 * Structured translation request.
 */
export interface TranslationBatchV1 {
  schema_version?: SchemaVersion;
  batch_id: BatchId;
  source_lang?: SourceLang;
  target_lang?: TargetLang;
  prompt_profile?: PromptProfile;
  segments?: Segments;
}
/**
 * A single block to translate.
 */
export interface TranslationSegment {
  segment_id: SegmentId;
  block_type?: BlockType;
  source_inline?: SourceInline;
  context?: SegmentContext;
  required_concepts?: RequiredConcepts;
  forbidden_targets?: ForbiddenTargets;
  locked_nodes?: LockedNodes;
  source_checksum?: SourceChecksum;
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
 * Contextual information for a translation segment.
 */
export interface SegmentContext {
  page_id?: PageId;
  section_path?: SectionPath;
  prev_heading?: PrevHeading;
}
