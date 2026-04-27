/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentVersion = string;
export type PresentationMode = 'article' | 'facsimile';
export type Id = string;
export type Title = string;
export type SectionPath = string[];
export type SourcePageNumber = number;
export type Prev = string | null;
export type Next = string | null;
export type ParentSection = string;
export type Kind = 'heading';
export type Id1 = string;
export type Level = number;
export type Kind1 = 'text';
export type Text = string;
export type Marks = string[];
export type Kind2 = 'icon';
export type SymbolId = string;
export type Alt = string;
export type Kind3 = 'figure_ref';
export type AssetId = string;
export type Label = string;
export type Children = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind4 = 'paragraph';
export type Id2 = string;
export type Children1 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind5 = 'figure';
export type Id3 = string;
export type AssetId1 = string;
export type Children2 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind6 = 'callout';
export type Id4 = string;
export type Variant = string;
export type Children3 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind7 = 'caption';
export type Id5 = string;
export type Children4 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind8 = 'table';
export type Id6 = string;
export type Kind9 = 'table_row';
export type Id7 = string;
export type Header = boolean;
export type Kind10 = 'table_cell';
export type Id8 = string;
export type Header1 = boolean;
export type Children6 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Cells = RenderTableCellBlock[];
export type Children5 = (RenderTextInline | RenderIconInline | RenderFigureRefInline | RenderTableRowBlock)[];
export type Kind11 = 'list_item';
export type Id9 = string;
export type Children7 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind12 = 'divider';
export type Id10 = string;
export type Blocks = (
  | RenderHeadingBlock
  | RenderParagraphBlock
  | RenderFigureBlock
  | RenderCalloutBlock
  | RenderCaptionBlock
  | RenderTableBlock
  | RenderListItemBlock
  | RenderDividerBlock
)[];
export type Src = string;
export type Alt1 = string;
export type Caption = string;
export type RasterSrc = string;
export type RasterSrcHires = string;
export type WidthPx = number;
export type HeightPx = number;
export type Text1 = string;
export type TranslatedText = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type Kind13 = 'title' | 'body' | 'caption' | 'callout' | 'label';
export type Priority = number;
export type Annotations = FacsimileAnnotation[];
export type GlossaryMentions = string[];
export type DocumentId = string;
export type PageId = string;
export type BlockRefs = string[];
export type BuildId = string;
export type GeneratedAt = string;

/**
 * Frontend-ready page payload.
 */
export interface RenderPageV1 {
  schema_version?: SchemaVersion;
  document_version?: DocumentVersion;
  presentation_mode?: PresentationMode;
  page: RenderPageMeta;
  nav?: RenderNav;
  blocks?: Blocks;
  figures?: Figures;
  facsimile?: RenderFacsimile | null;
  glossary_mentions?: GlossaryMentions;
  search?: Search;
  source_map?: RenderSourceMap | null;
  build_meta?: RenderBuildMeta | null;
}
export interface RenderPageMeta {
  id: Id;
  title?: Title;
  section_path?: SectionPath;
  source_page_number?: SourcePageNumber;
}
export interface RenderNav {
  prev?: Prev;
  next?: Next;
  parent_section?: ParentSection;
}
export interface RenderHeadingBlock {
  kind?: Kind;
  id: Id1;
  level?: Level;
  children?: Children;
}
export interface RenderTextInline {
  kind?: Kind1;
  text: Text;
  marks?: Marks;
}
export interface RenderIconInline {
  kind?: Kind2;
  symbol_id: SymbolId;
  alt?: Alt;
}
export interface RenderFigureRefInline {
  kind?: Kind3;
  asset_id: AssetId;
  label?: Label;
}
export interface RenderParagraphBlock {
  kind?: Kind4;
  id: Id2;
  children?: Children1;
}
export interface RenderFigureBlock {
  kind?: Kind5;
  id: Id3;
  asset_id?: AssetId1;
  children?: Children2;
}
export interface RenderCalloutBlock {
  kind?: Kind6;
  id: Id4;
  variant?: Variant;
  children?: Children3;
}
/**
 * S5U-737 — orphan caption rendered as a top-level block.
 *
 * Captions whose ``figure_block_id`` resolves to a ``FigureBlock`` on the
 * page are folded into ``RenderFigure.caption`` (S5U-700). Orphan captions
 * (no ``figure_block_id`` or a pointer that does not resolve) would
 * otherwise be silently dropped at render — they are now emitted here so
 * the translatable prose survives to the reader. Every
 * ``RenderCaptionBlock`` is orphan by construction; the reader stylizes
 * via ``data-orphan="true"``.
 */
export interface RenderCaptionBlock {
  kind?: Kind7;
  id: Id5;
  children?: Children4;
}
/**
 * S5U-704 — ``children`` may carry legacy flat inlines or
 * ``RenderTableRowBlock`` rows.  The table is "structured" iff any
 * child is a ``RenderTableRowBlock``.
 */
export interface RenderTableBlock {
  kind?: Kind8;
  id: Id6;
  children?: Children5;
}
/**
 * S5U-704 — a row of ``RenderTableCellBlock`` cells.
 */
export interface RenderTableRowBlock {
  kind?: Kind9;
  id: Id7;
  header?: Header;
  cells?: Cells;
}
/**
 * S5U-704 — a structured table cell.
 */
export interface RenderTableCellBlock {
  kind?: Kind10;
  id: Id8;
  header?: Header1;
  children?: Children6;
}
export interface RenderListItemBlock {
  kind?: Kind11;
  id: Id9;
  children?: Children7;
}
export interface RenderDividerBlock {
  kind?: Kind12;
  id: Id10;
}
export interface Figures {
  [k: string]: RenderFigure;
}
export interface RenderFigure {
  src: Src;
  alt?: Alt1;
  caption?: Caption;
}
/**
 * Raster metadata for facsimile page presentation.
 */
export interface RenderFacsimile {
  raster_src: RasterSrc;
  raster_src_hires?: RasterSrcHires;
  width_px?: WidthPx;
  height_px?: HeightPx;
  annotations?: Annotations;
}
/**
 * Positioned text overlay on a facsimile raster.
 */
export interface FacsimileAnnotation {
  text: Text1;
  translated_text?: TranslatedText;
  bbox: NormRect;
  kind?: Kind13;
  priority?: Priority;
}
/**
 * Bounding box in normalized [0,1] page coordinate space.
 */
export interface NormRect {
  x0: X0;
  y0: Y0;
  x1: X1;
  y1: Y1;
}
export interface Search {
  [k: string]: string | string[];
}
/**
 * Provenance back to the source IR for a render page.
 *
 * ``document_id`` is the parent document identifier (e.g.
 * ``"ato_core_v1_1"``); ``page_id`` is the single-page id
 * (e.g. ``"p0054"``). Both fields live here so QA rules
 * that walk render pages can emit per-document *and* per-page
 * records without threading the ids through every rule signature.
 *
 * ``document_id`` defaults to ``""`` for backward compatibility with
 * render_page.v1 payloads produced before S5U-735; the render stage
 * populates it from ``page_ir.document_id`` going forward.
 */
export interface RenderSourceMap {
  document_id?: DocumentId;
  page_id: PageId;
  block_refs?: BlockRefs;
}
export interface RenderBuildMeta {
  build_id?: BuildId;
  generated_at?: GeneratedAt;
}
