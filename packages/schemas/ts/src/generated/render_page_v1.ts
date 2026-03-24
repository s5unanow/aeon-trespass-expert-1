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
export type Kind7 = 'table';
export type Id5 = string;
export type Children4 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind8 = 'list_item';
export type Id6 = string;
export type Children5 = (RenderTextInline | RenderIconInline | RenderFigureRefInline)[];
export type Kind9 = 'divider';
export type Id7 = string;
export type Blocks = (
  | RenderHeadingBlock
  | RenderParagraphBlock
  | RenderFigureBlock
  | RenderCalloutBlock
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
export type GlossaryMentions = string[];
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
export interface RenderTableBlock {
  kind?: Kind7;
  id: Id5;
  children?: Children4;
}
export interface RenderListItemBlock {
  kind?: Kind8;
  id: Id6;
  children?: Children5;
}
export interface RenderDividerBlock {
  kind?: Kind9;
  id: Id7;
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
}
export interface Search {
  [k: string]: string | string[];
}
export interface RenderSourceMap {
  page_id: PageId;
  block_refs?: BlockRefs;
}
export interface RenderBuildMeta {
  build_id?: BuildId;
  generated_at?: GeneratedAt;
}
