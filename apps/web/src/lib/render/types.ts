/**
 * Schema-derived render types for the reader.
 *
 * All types are mechanically projected from the generated `@atr/schemas`
 * package — the single source of truth is Python Pydantic, via JSON Schema,
 * to the generated TS in `packages/schemas/ts/src/generated/render_page_v1.ts`.
 *
 * This file narrows the generated (loose) schema types into a reader-local
 * projection where defaulted fields are materialized as required. The
 * materialization is performed at runtime by `normalizeRenderPage`; the
 * types below express the post-normalization shape so components can consume
 * them without defensive null checks.
 *
 * Adding a new block or inline kind to the Pydantic source + regenerating
 * schemas lands in `renderPageV1.Blocks[number]` / `renderPageV1.Children[number]`
 * automatically. The exhaustive `switch` in `BlockRenderer` / `InlineRenderer`
 * and `normalizeRenderPage` then fails to compile on the `never` branch until
 * the new kind is wired — this is the "additive schema change fails fast"
 * invariant documented in S5U-685.
 */

import type { renderPageV1 } from '@atr/schemas';

// ---------------------------------------------------------------------------
// Utility projections
// ---------------------------------------------------------------------------

/** Materialize a defaulted discriminator `kind` into a required field. */
type NarrowKind<T extends { kind?: string }> = Omit<T, 'kind'> & {
  kind: NonNullable<T['kind']>;
};

/**
 * Materialize both the defaulted `kind` discriminator and the defaulted
 * `children` array into required fields using the reader-local inline union.
 */
type NarrowBlock<T extends { kind?: string; children?: unknown }> = Omit<T, 'kind' | 'children'> & {
  kind: NonNullable<T['kind']>;
  children: RenderInlineNode[];
};

// ---------------------------------------------------------------------------
// Inline nodes — projected from renderPageV1
// ---------------------------------------------------------------------------

export type RenderTextInline = NarrowKind<renderPageV1.RenderTextInline> & {
  marks: string[];
};
export type RenderIconInline = NarrowKind<renderPageV1.RenderIconInline> & {
  alt: string;
};
export type RenderFigureRefInline = NarrowKind<renderPageV1.RenderFigureRefInline> & {
  label: string;
};

export type RenderInlineNode = RenderTextInline | RenderIconInline | RenderFigureRefInline;

// ---------------------------------------------------------------------------
// Block nodes — projected from renderPageV1
// ---------------------------------------------------------------------------

export type RenderHeadingBlock = NarrowBlock<renderPageV1.RenderHeadingBlock> & {
  level: number;
};
export type RenderParagraphBlock = NarrowBlock<renderPageV1.RenderParagraphBlock>;
export type RenderFigureBlock = NarrowBlock<renderPageV1.RenderFigureBlock> & {
  asset_id: string;
};
export type RenderCalloutBlock = NarrowBlock<renderPageV1.RenderCalloutBlock> & {
  variant: string;
};
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
// Page-level types — projected from renderPageV1
// ---------------------------------------------------------------------------

export type RenderPageMeta = Required<renderPageV1.RenderPageMeta>;
export type RenderNav = Required<renderPageV1.RenderNav>;
export type RenderFigure = renderPageV1.RenderFigure;
export type RenderFacsimile = renderPageV1.RenderFacsimile;
export type FacsimileAnnotation = renderPageV1.FacsimileAnnotation;
export type RenderSourceMap = Required<renderPageV1.RenderSourceMap>;
export type RenderBuildMeta = renderPageV1.RenderBuildMeta;

/**
 * Reader-local projection of `RenderPageV1` with all defaulted fields
 * materialized. Produced only by `normalizeRenderPage`.
 */
export interface RenderPageData {
  schema_version: NonNullable<renderPageV1.RenderPageV1['schema_version']>;
  document_version: NonNullable<renderPageV1.RenderPageV1['document_version']>;
  presentation_mode: NonNullable<renderPageV1.RenderPageV1['presentation_mode']>;
  page: RenderPageMeta;
  nav: RenderNav;
  blocks: RenderBlock[];
  figures: Record<string, RenderFigure>;
  facsimile: RenderFacsimile | null;
  glossary_mentions: string[];
  source_map: RenderSourceMap | null;
  build_meta: RenderBuildMeta | null;
  search: Record<string, string | string[]>;
}
