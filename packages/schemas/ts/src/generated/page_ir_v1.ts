/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
export type LanguageCode = 'en' | 'ru';
export type Width = number;
export type Height = number;
export type SectionId = string;
export type Path = string[];
export type Type = 'heading';
export type BlockId = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type Level = number;
export type Type1 = 'text';
export type Text = string;
export type Marks = string[];
export type SourceWordIds = string[];
export type Type2 = 'icon';
export type SymbolId = string;
export type InstanceId = string;
export type SourceAssetId = string;
/**
 * How a symbol attaches to its context.
 */
export type SymbolAnchorKind = 'inline' | 'prefix' | 'cell_local' | 'block_attached' | 'region_annotation';
export type Confidence = number;
export type Type3 = 'figure_ref';
export type AssetId = string;
export type Label = string;
export type Type4 = 'xref';
export type TargetPageId = string;
export type TargetSectionId = string;
export type Label1 = string;
export type Type5 = 'line_break';
export type Type6 = 'term_mark';
export type ConceptId = string;
export type SurfaceForm = string;
export type Children = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable = boolean;
export type FontName = string;
export type FontSize = number;
export type IsBold = boolean;
export type IsItalic = boolean;
export type PageId1 = string;
export type WordIds = string[];
export type EvidenceRefs = string[];
export type ConceptHits = string[];
export type SourceConfidence = number;
export type Type7 = 'paragraph';
export type BlockId1 = string;
export type Children1 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable1 = boolean;
export type Type8 = 'list';
export type BlockId2 = string;
export type Ordered = boolean;
export type Children2 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable2 = boolean;
export type Type9 = 'list_item';
export type BlockId3 = string;
export type Children3 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable3 = boolean;
export type Type10 = 'table';
export type BlockId4 = string;
export type Type11 = 'table_row';
export type BlockId5 = string;
export type Header = boolean;
export type Type12 = 'table_cell';
export type BlockId6 = string;
export type Header1 = boolean;
export type Children5 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable4 = boolean;
export type Cells = TableCellBlock[];
export type Translatable5 = boolean;
export type Children4 = (
  | TextInline
  | IconInline
  | FigureRefInline
  | XrefInline
  | LineBreakInline
  | TermMarkInline
  | TableRowBlock
)[];
export type Translatable6 = boolean;
export type Type13 = 'callout';
export type BlockId7 = string;
export type RegionId = string;
export type Variant = string;
export type Children6 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable7 = boolean;
export type Type14 = 'figure';
export type BlockId8 = string;
export type AssetId1 = string;
export type Children7 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable8 = boolean;
export type Type15 = 'caption';
export type BlockId9 = string;
export type FigureBlockId = string;
export type Children8 = (TextInline | IconInline | FigureRefInline | XrefInline | LineBreakInline | TermMarkInline)[];
export type Translatable9 = boolean;
export type Type16 = 'divider';
export type BlockId10 = string;
export type Translatable10 = boolean;
export type Type17 = 'unknown';
export type BlockId11 = string;
export type RawText = string;
export type Translatable11 = boolean;
export type Blocks = (
  | HeadingBlock
  | ParagraphBlock
  | ListBlock
  | ListItemBlock
  | TableBlock
  | CalloutBlock
  | FigureBlock
  | CaptionBlock
  | DividerBlock
  | UnknownBlock
)[];
export type Assets = string[];
export type ReadingOrder = string[];
export type NativeTextCoverage = number;
export type ReadingOrderScore = number;
export type SymbolScore = number;
export type PageConfidence = number;
export type Blocking = boolean;
export type Errors = number;
export type Warnings = number;
export type Extractor = string;
export type Version = string;
export type EvidenceIds = string[];

/**
 * Canonical page content IR.
 */
export interface PageIRV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  language: LanguageCode;
  dimensions_pt?: PageDimensions | null;
  section_hint?: SectionHint | null;
  blocks?: Blocks;
  assets?: Assets;
  reading_order?: ReadingOrder;
  confidence?: ConfidenceMetrics | null;
  qa_state?: QAState | null;
  provenance?: ProvenanceRef | null;
}
/**
 * Source page dimensions in PDF points.
 */
export interface PageDimensions {
  width: Width;
  height: Height;
}
/**
 * Section context for a page.
 */
export interface SectionHint {
  section_id?: SectionId;
  path?: Path;
}
/**
 * Heading block.
 */
export interface HeadingBlock {
  type?: Type;
  block_id: BlockId;
  bbox?: Rect | null;
  level?: Level;
  children?: Children;
  translatable?: Translatable;
  style_hint?: StyleHint | null;
  source_ref?: SourceRef | null;
  annotations?: BlockAnnotations | null;
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
 * Plain text inline node.
 */
export interface TextInline {
  type?: Type1;
  text: Text;
  marks?: Marks;
  lang?: LanguageCode | null;
  source_word_ids?: SourceWordIds;
}
/**
 * Inline icon node, recovered from symbol catalog matching.
 */
export interface IconInline {
  type?: Type2;
  symbol_id: SymbolId;
  instance_id?: InstanceId;
  bbox?: Rect | null;
  display_hint?: DisplayHint;
  source_asset_id?: SourceAssetId;
  anchor_kind?: SymbolAnchorKind | null;
  confidence?: Confidence;
}
export interface DisplayHint {
  [k: string]: number | boolean;
}
/**
 * Inline reference to a figure asset.
 */
export interface FigureRefInline {
  type?: Type3;
  asset_id: AssetId;
  label?: Label;
}
/**
 * Cross-reference to another page or section.
 */
export interface XrefInline {
  type?: Type4;
  target_page_id?: TargetPageId;
  target_section_id?: TargetSectionId;
  label?: Label1;
}
/**
 * Explicit line break.
 */
export interface LineBreakInline {
  type?: Type5;
}
/**
 * Glossary term marker.
 */
export interface TermMarkInline {
  type?: Type6;
  concept_id: ConceptId;
  surface_form?: SurfaceForm;
}
/**
 * Font/spacing/classification hints for a block.
 */
export interface StyleHint {
  font_name?: FontName;
  font_size?: FontSize;
  is_bold?: IsBold;
  is_italic?: IsItalic;
}
/**
 * Source evidence references for a block.
 */
export interface SourceRef {
  page_id?: PageId1;
  word_ids?: WordIds;
  evidence_refs?: EvidenceRefs;
}
/**
 * Annotations attached to a block.
 */
export interface BlockAnnotations {
  concept_hits?: ConceptHits;
  source_confidence?: SourceConfidence;
}
/**
 * Paragraph block.
 */
export interface ParagraphBlock {
  type?: Type7;
  block_id: BlockId1;
  bbox?: Rect | null;
  children?: Children1;
  translatable?: Translatable1;
  style_hint?: StyleHint | null;
  source_ref?: SourceRef | null;
  annotations?: BlockAnnotations | null;
}
/**
 * List container block.
 */
export interface ListBlock {
  type?: Type8;
  block_id: BlockId2;
  bbox?: Rect | null;
  ordered?: Ordered;
  children?: Children2;
  translatable?: Translatable2;
  source_ref?: SourceRef | null;
}
/**
 * List item block.
 */
export interface ListItemBlock {
  type?: Type9;
  block_id: BlockId3;
  bbox?: Rect | null;
  children?: Children3;
  translatable?: Translatable3;
  source_ref?: SourceRef | null;
}
/**
 * Table block.
 *
 * S5U-704 — ``children`` widened to accept either the legacy flat
 * ``InlineNode`` sequence (back-compat for cached artifacts and simple
 * cases) or a list of ``TableRowBlock`` rows with structured cells.
 * The two forms may be mixed but readers should treat the table as
 * "structured" iff any child is a ``TableRowBlock``.
 */
export interface TableBlock {
  type?: Type10;
  block_id: BlockId4;
  bbox?: Rect | null;
  children?: Children4;
  translatable?: Translatable6;
  source_ref?: SourceRef | null;
}
/**
 * Row inside a TableBlock.
 *
 * S5U-704 — a ``TableRowBlock`` groups one or more ``TableCellBlock``
 * children. Only meaningful inside a ``TableBlock``.
 */
export interface TableRowBlock {
  type?: Type11;
  block_id: BlockId5;
  bbox?: Rect | null;
  header?: Header;
  cells?: Cells;
  translatable?: Translatable5;
  source_ref?: SourceRef | null;
}
/**
 * Cell inside a TableRowBlock.
 *
 * S5U-704 — structured chart/table cells carry their own inline run.
 * A ``TableCellBlock`` is only meaningful inside a ``TableRowBlock``;
 * its ``children`` field is the familiar inline union.
 */
export interface TableCellBlock {
  type?: Type12;
  block_id: BlockId6;
  bbox?: Rect | null;
  header?: Header1;
  children?: Children5;
  translatable?: Translatable4;
  source_ref?: SourceRef | null;
}
/**
 * Callout/sidebar block.
 */
export interface CalloutBlock {
  type?: Type13;
  block_id: BlockId7;
  bbox?: Rect | null;
  region_id?: RegionId;
  variant?: Variant;
  children?: Children6;
  translatable?: Translatable7;
  source_ref?: SourceRef | null;
}
/**
 * Figure block.
 */
export interface FigureBlock {
  type?: Type14;
  block_id: BlockId8;
  bbox?: Rect | null;
  asset_id?: AssetId1;
  children?: Children7;
  translatable?: Translatable8;
  source_ref?: SourceRef | null;
}
/**
 * Caption block.
 */
export interface CaptionBlock {
  type?: Type15;
  block_id: BlockId9;
  bbox?: Rect | null;
  figure_block_id?: FigureBlockId;
  children?: Children8;
  translatable?: Translatable9;
  source_ref?: SourceRef | null;
}
/**
 * Divider/rule block.
 */
export interface DividerBlock {
  type?: Type16;
  block_id: BlockId10;
  bbox?: Rect | null;
  translatable?: Translatable10;
}
/**
 * Unknown block — allowed only pre-publish.
 */
export interface UnknownBlock {
  type?: Type17;
  block_id: BlockId11;
  bbox?: Rect | null;
  raw_text?: RawText;
  translatable?: Translatable11;
  source_ref?: SourceRef | null;
}
/**
 * Per-page confidence scores.
 */
export interface ConfidenceMetrics {
  native_text_coverage: NativeTextCoverage;
  reading_order_score?: ReadingOrderScore;
  symbol_score?: SymbolScore;
  page_confidence?: PageConfidence;
}
/**
 * Page-level QA status summary.
 */
export interface QAState {
  blocking?: Blocking;
  errors?: Errors;
  warnings?: Warnings;
}
/**
 * Reference to upstream evidence or extraction source.
 */
export interface ProvenanceRef {
  extractor: Extractor;
  version: Version;
  evidence_ids?: EvidenceIds;
}
