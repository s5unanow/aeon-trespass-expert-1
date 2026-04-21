/**
 * Runtime normalization of `render_page.v1` payloads at the reader fetch
 * boundary.
 *
 * The generated TS type (`renderPageV1.RenderPageV1`) encodes the JSON Schema
 * "everything-optional-with-Pydantic-defaults" shape. The reader components
 * consume a narrowed projection (`RenderPageData`) where defaulted fields are
 * materialized. This module is the one place that materializes those defaults
 * and rejects unknown block/inline kinds — downstream code never reads from
 * the raw `unknown` JSON.
 *
 * Additive schema evolution is guarded by exhaustive `switch` blocks whose
 * `never` branch fails to typecheck once a new kind lands in the generated
 * union — see the `_exhaustive: never` lines below. This is the "fail-fast on
 * new kinds" invariant documented in S5U-685.
 */

import type {
  RenderBlock,
  RenderFigure,
  RenderInlineNode,
  RenderPageData,
  RenderPageMeta,
  RenderNav,
  RenderFacsimile,
  FacsimileAnnotation,
  RenderSourceMap,
  RenderBuildMeta,
} from './types';

/** Thrown when a `render_page.v1` payload cannot be normalized to `RenderPageData`. */
export class InvalidRenderPageError extends Error {
  readonly path: string;
  constructor(path: string, detail: string) {
    super(`Invalid render_page payload at ${path}: ${detail}`);
    this.name = 'InvalidRenderPageError';
    this.path = path;
  }
}

const SUPPORTED_SCHEMA_VERSION = 'render_page.v1';

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function asArray(v: unknown, path: string): unknown[] {
  if (v === undefined) return [];
  if (!Array.isArray(v)) {
    throw new InvalidRenderPageError(path, `expected array, got ${typeof v}`);
  }
  return v;
}

function asString(v: unknown, path: string, fallback?: string): string {
  if (v === undefined || v === null) {
    if (fallback !== undefined) return fallback;
    throw new InvalidRenderPageError(path, 'missing required string');
  }
  if (typeof v !== 'string') {
    throw new InvalidRenderPageError(path, `expected string, got ${typeof v}`);
  }
  return v;
}

function asStringArray(v: unknown, path: string): string[] {
  const arr = asArray(v, path);
  return arr.map((item, i) => asString(item, `${path}[${i}]`));
}

function asNumber(v: unknown, path: string, fallback: number): number {
  if (v === undefined || v === null) return fallback;
  if (typeof v !== 'number' || Number.isNaN(v)) {
    throw new InvalidRenderPageError(path, `expected number, got ${typeof v}`);
  }
  return v;
}

// ---------------------------------------------------------------------------
// Inline nodes
// ---------------------------------------------------------------------------

function normalizeInline(raw: unknown, path: string): RenderInlineNode {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected inline node object, got ${typeof raw}`);
  }
  const kind = asString(raw.kind, `${path}.kind`);
  switch (kind) {
    case 'text':
      return {
        kind: 'text',
        text: asString(raw.text, `${path}.text`),
        marks: asStringArray(raw.marks ?? [], `${path}.marks`),
      };
    case 'icon':
      return {
        kind: 'icon',
        symbol_id: asString(raw.symbol_id, `${path}.symbol_id`),
        alt: asString(raw.alt, `${path}.alt`, ''),
      };
    case 'figure_ref':
      return {
        kind: 'figure_ref',
        asset_id: asString(raw.asset_id, `${path}.asset_id`),
        label: asString(raw.label, `${path}.label`, ''),
      };
    default:
      throw new InvalidRenderPageError(`${path}.kind`, `unsupported inline kind "${kind}"`);
  }
}

function normalizeInlines(raw: unknown, path: string): RenderInlineNode[] {
  return asArray(raw, path).map((node, i) => normalizeInline(node, `${path}[${i}]`));
}

// ---------------------------------------------------------------------------
// Blocks
// ---------------------------------------------------------------------------

function normalizeBlock(raw: unknown, path: string): RenderBlock {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected block object, got ${typeof raw}`);
  }
  const id = asString(raw.id, `${path}.id`);
  const kind = asString(raw.kind, `${path}.kind`);
  switch (kind) {
    case 'heading':
      return {
        kind: 'heading',
        id,
        level: asNumber(raw.level, `${path}.level`, 1),
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'paragraph':
      return {
        kind: 'paragraph',
        id,
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'figure':
      return {
        kind: 'figure',
        id,
        asset_id: asString(raw.asset_id, `${path}.asset_id`, ''),
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'callout':
      return {
        kind: 'callout',
        id,
        variant: asString(raw.variant, `${path}.variant`, ''),
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'table':
      return {
        kind: 'table',
        id,
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'list_item':
      return {
        kind: 'list_item',
        id,
        children: normalizeInlines(raw.children ?? [], `${path}.children`),
      };
    case 'divider':
      return { kind: 'divider', id };
    default:
      throw new InvalidRenderPageError(`${path}.kind`, `unsupported block kind "${kind}"`);
  }
}

// ---------------------------------------------------------------------------
// Page-level members
// ---------------------------------------------------------------------------

function normalizePageMeta(raw: unknown): RenderPageMeta {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('page', `expected object, got ${typeof raw}`);
  }
  return {
    id: asString(raw.id, 'page.id'),
    title: asString(raw.title, 'page.title', ''),
    section_path: asStringArray(raw.section_path ?? [], 'page.section_path'),
    source_page_number: asNumber(raw.source_page_number, 'page.source_page_number', 0),
  };
}

function normalizeNav(raw: unknown): RenderNav {
  if (raw === undefined || raw === null) {
    return { prev: null, next: null, parent_section: '' };
  }
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('nav', `expected object, got ${typeof raw}`);
  }
  const prev = raw.prev;
  const next = raw.next;
  return {
    prev: prev === null || prev === undefined ? null : asString(prev, 'nav.prev'),
    next: next === null || next === undefined ? null : asString(next, 'nav.next'),
    parent_section: asString(raw.parent_section, 'nav.parent_section', ''),
  };
}

function normalizeFigures(raw: unknown): Record<string, RenderFigure> {
  if (raw === undefined) return {};
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('figures', `expected object, got ${typeof raw}`);
  }
  const out: Record<string, RenderFigure> = {};
  for (const [assetId, figRaw] of Object.entries(raw)) {
    if (!isObject(figRaw)) {
      throw new InvalidRenderPageError(
        `figures.${assetId}`,
        `expected object, got ${typeof figRaw}`,
      );
    }
    out[assetId] = {
      src: asString(figRaw.src, `figures.${assetId}.src`),
      alt: asString(figRaw.alt, `figures.${assetId}.alt`, ''),
      caption: asString(figRaw.caption, `figures.${assetId}.caption`, ''),
    };
  }
  return out;
}

function normalizeFacsimileAnnotation(raw: unknown, path: string): FacsimileAnnotation {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected object, got ${typeof raw}`);
  }
  const bboxRaw = raw.bbox;
  if (!isObject(bboxRaw)) {
    throw new InvalidRenderPageError(`${path}.bbox`, `expected object, got ${typeof bboxRaw}`);
  }
  const kindRaw = raw.kind;
  const kind = kindRaw === undefined ? 'body' : asString(kindRaw, `${path}.kind`);
  if (
    kind !== 'title' &&
    kind !== 'body' &&
    kind !== 'caption' &&
    kind !== 'callout' &&
    kind !== 'label'
  ) {
    throw new InvalidRenderPageError(`${path}.kind`, `unsupported annotation kind "${kind}"`);
  }
  return {
    text: asString(raw.text, `${path}.text`),
    translated_text: asString(raw.translated_text, `${path}.translated_text`, ''),
    bbox: {
      x0: asNumber(bboxRaw.x0, `${path}.bbox.x0`, 0),
      y0: asNumber(bboxRaw.y0, `${path}.bbox.y0`, 0),
      x1: asNumber(bboxRaw.x1, `${path}.bbox.x1`, 0),
      y1: asNumber(bboxRaw.y1, `${path}.bbox.y1`, 0),
    },
    kind,
    priority: asNumber(raw.priority, `${path}.priority`, 0),
  };
}

function normalizeFacsimile(raw: unknown): RenderFacsimile | null {
  if (raw === undefined || raw === null) return null;
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('facsimile', `expected object, got ${typeof raw}`);
  }
  const annotationsRaw = asArray(raw.annotations ?? [], 'facsimile.annotations');
  return {
    raster_src: asString(raw.raster_src, 'facsimile.raster_src'),
    raster_src_hires: asString(raw.raster_src_hires, 'facsimile.raster_src_hires', ''),
    width_px: asNumber(raw.width_px, 'facsimile.width_px', 0),
    height_px: asNumber(raw.height_px, 'facsimile.height_px', 0),
    annotations: annotationsRaw.map((ann, i) =>
      normalizeFacsimileAnnotation(ann, `facsimile.annotations[${i}]`),
    ),
  };
}

function normalizeSourceMap(raw: unknown): RenderSourceMap | null {
  if (raw === undefined || raw === null) return null;
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('source_map', `expected object, got ${typeof raw}`);
  }
  return {
    page_id: asString(raw.page_id, 'source_map.page_id'),
    block_refs: asStringArray(raw.block_refs ?? [], 'source_map.block_refs'),
  };
}

function normalizeBuildMeta(raw: unknown): RenderBuildMeta | null {
  if (raw === undefined || raw === null) return null;
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('build_meta', `expected object, got ${typeof raw}`);
  }
  return {
    build_id: asString(raw.build_id, 'build_meta.build_id', ''),
    generated_at: asString(raw.generated_at, 'build_meta.generated_at', ''),
  };
}

function normalizeSearch(raw: unknown): Record<string, string | string[]> {
  if (raw === undefined) return {};
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('search', `expected object, got ${typeof raw}`);
  }
  const out: Record<string, string | string[]> = {};
  for (const [k, val] of Object.entries(raw)) {
    if (typeof val === 'string') {
      out[k] = val;
    } else if (Array.isArray(val)) {
      out[k] = val.map((item, i) => asString(item, `search.${k}[${i}]`));
    } else {
      throw new InvalidRenderPageError(
        `search.${k}`,
        `expected string or string[], got ${typeof val}`,
      );
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Top-level
// ---------------------------------------------------------------------------

export function normalizeRenderPage(raw: unknown): RenderPageData {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError('$', `expected object, got ${typeof raw}`);
  }
  const schema_version = asString(raw.schema_version, 'schema_version', SUPPORTED_SCHEMA_VERSION);
  if (schema_version !== SUPPORTED_SCHEMA_VERSION) {
    throw new InvalidRenderPageError(
      'schema_version',
      `unsupported "${schema_version}"; expected "${SUPPORTED_SCHEMA_VERSION}"`,
    );
  }
  const presentationRaw = raw.presentation_mode;
  const presentation_mode =
    presentationRaw === undefined ? 'article' : asString(presentationRaw, 'presentation_mode');
  if (presentation_mode !== 'article' && presentation_mode !== 'facsimile') {
    throw new InvalidRenderPageError(
      'presentation_mode',
      `unsupported "${presentation_mode}"; expected "article" | "facsimile"`,
    );
  }

  const blocksRaw = asArray(raw.blocks ?? [], 'blocks');
  const blocks = blocksRaw.map((b, i) => normalizeBlock(b, `blocks[${i}]`));

  return {
    schema_version,
    document_version: asString(raw.document_version, 'document_version', ''),
    presentation_mode,
    page: normalizePageMeta(raw.page),
    nav: normalizeNav(raw.nav),
    blocks,
    figures: normalizeFigures(raw.figures),
    facsimile: normalizeFacsimile(raw.facsimile),
    glossary_mentions: asStringArray(raw.glossary_mentions ?? [], 'glossary_mentions'),
    source_map: normalizeSourceMap(raw.source_map),
    build_meta: normalizeBuildMeta(raw.build_meta),
    search: normalizeSearch(raw.search),
  };
}
