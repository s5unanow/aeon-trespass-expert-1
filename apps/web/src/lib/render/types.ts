/**
 * Lightweight render types matching RenderPageV1 schema.
 * These are hand-written for clean component props — the generated
 * types from @atr/schemas serve as the contract reference.
 */

// --- Inline nodes ---

export interface RenderTextInline {
  kind: 'text';
  text: string;
  marks?: string[];
}

export interface RenderIconInline {
  kind: 'icon';
  symbol_id: string;
  alt?: string;
}

export interface RenderFigureRefInline {
  kind: 'figure_ref';
  asset_id: string;
  label?: string;
}

export type RenderInlineNode = RenderTextInline | RenderIconInline | RenderFigureRefInline;

// --- Block nodes ---

export interface RenderHeadingBlock {
  kind: 'heading';
  id: string;
  level: number;
  children: RenderInlineNode[];
}

export interface RenderParagraphBlock {
  kind: 'paragraph';
  id: string;
  children: RenderInlineNode[];
}

export interface RenderFigureBlock {
  kind: 'figure';
  id: string;
  asset_id?: string;
  children: RenderInlineNode[];
}

export interface RenderListItemBlock {
  kind: 'list_item';
  id: string;
  children: RenderInlineNode[];
}

export interface RenderDividerBlock {
  kind: 'divider';
  id: string;
}

export type RenderBlock =
  | RenderHeadingBlock
  | RenderParagraphBlock
  | RenderFigureBlock
  | RenderListItemBlock
  | RenderDividerBlock;

// --- Page-level ---

export interface RenderPageMeta {
  id: string;
  title: string;
  section_path: string[];
  source_page_number: number;
}

export interface RenderNav {
  prev: string | null;
  next: string | null;
  parent_section: string;
}

export interface RenderFigure {
  src: string;
  alt?: string;
  caption?: string;
}

export interface RenderSourceMap {
  page_id: string;
  block_refs: string[];
}

export interface RenderPageData {
  schema_version: string;
  document_version: string;
  page: RenderPageMeta;
  nav: RenderNav;
  blocks: RenderBlock[];
  figures: Record<string, RenderFigure>;
  glossary_mentions: string[];
  source_map: RenderSourceMap | null;
}
