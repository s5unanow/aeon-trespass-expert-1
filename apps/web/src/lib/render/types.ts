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
export type RenderCaptionBlock = NarrowBlock<renderPageV1.RenderCaptionBlock>;

// S5U-704 — table rows/cells are nested structured children of a table block.
export type RenderTableCellBlock = Omit<
  NarrowKind<renderPageV1.RenderTableCellBlock>,
  'children' | 'header'
> & {
  kind: 'table_cell';
  header: boolean;
  children: RenderInlineNode[];
};
export type RenderTableRowBlock = Omit<
  NarrowKind<renderPageV1.RenderTableRowBlock>,
  'cells' | 'header'
> & {
  kind: 'table_row';
  header: boolean;
  cells: RenderTableCellBlock[];
};

/**
 * A table's child may be a legacy flat inline or a structured
 * `RenderTableRowBlock`. The reader treats the block as "structured" iff
 * any child is a row.
 */
export type RenderTableChild = RenderInlineNode | RenderTableRowBlock;

export type RenderTableBlock = Omit<NarrowBlock<renderPageV1.RenderTableBlock>, 'children'> & {
  children: RenderTableChild[];
};
export type RenderListItemBlock = NarrowBlock<renderPageV1.RenderListItemBlock>;
export type RenderDividerBlock = NarrowKind<renderPageV1.RenderDividerBlock>;

export type RenderBlock =
  | RenderHeadingBlock
  | RenderParagraphBlock
  | RenderFigureBlock
  | RenderCalloutBlock
  | RenderCaptionBlock
  | RenderTableBlock
  | RenderListItemBlock
  | RenderDividerBlock;

// ---------------------------------------------------------------------------
// Compile-time coverage guard — additive schema evolution
// ---------------------------------------------------------------------------

/**
 * Resolves to `true` when every `kind` discriminator in `Generated` is also
 * present on `Narrowed`, and to `never` otherwise. When a new block or
 * inline kind lands in the generated schema and is not yet mirrored in
 * `RenderBlock` / `RenderInlineNode` below, the assignments at the bottom of
 * this file fail to typecheck — forcing the worker to extend the reader
 * surface in the same change. This is the compile-time half of the
 * "additive schema change fails fast" invariant documented in S5U-685.
 */
type UnionHasAllKinds<Generated extends { kind?: string }, Narrowed extends { kind: string }> =
  Exclude<NonNullable<Generated['kind']>, Narrowed['kind']> extends never ? true : never;

// The two constants below are the tripwire. Do not delete them; regenerating
// `render_page_v1.ts` with a new kind flips the corresponding alias to `never`,
// which breaks compilation here and nowhere else obvious.
const _blockKindsCovered: UnionHasAllKinds<renderPageV1.Blocks[number], RenderBlock> = true;
const _inlineKindsCovered: UnionHasAllKinds<renderPageV1.Children[number], RenderInlineNode> = true;
void _blockKindsCovered;
void _inlineKindsCovered;

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

/** `RenderPageV1.presentation_mode` enum, projected from the generated schema. */
export type PresentationMode = NonNullable<renderPageV1.RenderPageV1['presentation_mode']>;

/** `FacsimileAnnotation.kind` enum, projected from the generated schema. */
export type FacsimileAnnotationKind = NonNullable<renderPageV1.FacsimileAnnotation['kind']>;

// ---------------------------------------------------------------------------
// Compile-time coverage guard — enum-valued schema fields
// ---------------------------------------------------------------------------

/**
 * Resolves to `true` when `Covered` is a superset of `Enum`, and to `never`
 * otherwise. Used to force the runtime tables in `normalize.ts` to list
 * every enum literal the generated schema admits. Adding a new literal to
 * Pydantic (e.g. a new `FacsimileAnnotation.kind` value or a new
 * `presentation_mode`) regenerates the TS enum, which flips this alias to
 * `never` until the runtime table is extended.
 */
export type AssertEnumCovered<Enum extends string, Covered extends Enum> =
  Exclude<Enum, Covered> extends never ? true : never;

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
