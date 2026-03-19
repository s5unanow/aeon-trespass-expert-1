/**
 * Schema-derived render types for the reader.
 *
 * All types are derived from the generated @atr/schemas package.
 * This adapter narrows optional fields to required for component
 * props while keeping the schema as the single source of truth.
 *
 * If the schema changes, these derivations fail at compile time.
 */

import type { renderPageV1 } from '@atr/schemas';

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

/** Make `kind` required for discriminated-union dispatch. */
type NarrowKind<T extends { kind?: string }> = Omit<T, 'kind'> & {
  kind: NonNullable<T['kind']>;
};

/** Make `kind` required and replace `children` with narrowed inline nodes. */
type NarrowBlock<T extends { kind?: string; children?: unknown }> = Omit<
  T,
  'kind' | 'children'
> & {
  kind: NonNullable<T['kind']>;
  children: RenderInlineNode[];
};

// ---------------------------------------------------------------------------
// Inline nodes
// ---------------------------------------------------------------------------

export type RenderTextInline = NarrowKind<renderPageV1.RenderTextInline>;
export type RenderIconInline = NarrowKind<renderPageV1.RenderIconInline>;
export type RenderFigureRefInline = NarrowKind<renderPageV1.RenderFigureRefInline>;

export type RenderInlineNode =
  | RenderTextInline
  | RenderIconInline
  | RenderFigureRefInline;

// ---------------------------------------------------------------------------
// Block nodes
// ---------------------------------------------------------------------------

export type RenderHeadingBlock = NarrowBlock<renderPageV1.RenderHeadingBlock> & {
  level: number;
};
export type RenderParagraphBlock = NarrowBlock<renderPageV1.RenderParagraphBlock>;
export type RenderFigureBlock = NarrowBlock<renderPageV1.RenderFigureBlock>;
export type RenderCalloutBlock = NarrowBlock<renderPageV1.RenderCalloutBlock>;
export type RenderTableBlock = NarrowBlock<renderPageV1.RenderTableBlock>;
export type RenderListItemBlock = NarrowBlock<renderPageV1.RenderListItemBlock>;
export type RenderDividerBlock = NarrowKind<renderPageV1.RenderDividerBlock>;

export type RenderBlock =
  | RenderHeadingBlock
  | RenderParagraphBlock
  | RenderFigureBlock
  | RenderCalloutBlock
  | RenderTableBlock
  | RenderListItemBlock
  | RenderDividerBlock;

// ---------------------------------------------------------------------------
// Page-level types
// ---------------------------------------------------------------------------

export type RenderPageMeta = Required<renderPageV1.RenderPageMeta>;
export type RenderNav = Required<renderPageV1.RenderNav>;
export type RenderFigure = renderPageV1.RenderFigure;
export type RenderSourceMap = Required<renderPageV1.RenderSourceMap>;

/** Frontend page payload — derived from RenderPageV1 with required fields. */
export interface RenderPageData {
  schema_version: NonNullable<renderPageV1.RenderPageV1['schema_version']>;
  document_version: NonNullable<renderPageV1.RenderPageV1['document_version']>;
  page: RenderPageMeta;
  nav: RenderNav;
  blocks: RenderBlock[];
  figures: Record<string, RenderFigure>;
  glossary_mentions: string[];
  source_map: RenderSourceMap | null;
}
