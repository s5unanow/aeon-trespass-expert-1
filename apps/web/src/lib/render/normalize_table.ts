/**
 * Normalizer helpers for `RenderTableBlock.children` (S5U-704).
 *
 * Extracted from `normalize.ts` to keep that file under the 400-line
 * file-length cap. The public entry points (`normalizeTableChildren`)
 * take an injected inline-normalizer so this module does not depend on
 * the block-level normalizer.
 */

import type {
  RenderInlineNode,
  RenderTableCellBlock,
  RenderTableChild,
  RenderTableRowBlock,
} from './types';
import {
  asArray,
  asBoolean,
  asString,
  InvalidRenderPageError,
  isObject,
} from './normalize_primitives';

type InlineNormalizer = (raw: unknown, path: string) => RenderInlineNode;

function normalizeTableCell(
  raw: unknown,
  path: string,
  normalizeInline: InlineNormalizer,
): RenderTableCellBlock {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected table_cell object, got ${typeof raw}`);
  }
  const kind = asString(raw.kind, `${path}.kind`);
  if (kind !== 'table_cell') {
    throw new InvalidRenderPageError(`${path}.kind`, `expected "table_cell", got "${kind}"`);
  }
  const childrenRaw = asArray(raw.children ?? [], `${path}.children`);
  return {
    kind: 'table_cell',
    id: asString(raw.id, `${path}.id`),
    header: asBoolean(raw.header, `${path}.header`, false),
    children: childrenRaw.map((node, i) => normalizeInline(node, `${path}.children[${i}]`)),
  };
}

function normalizeTableRow(
  raw: unknown,
  path: string,
  normalizeInline: InlineNormalizer,
): RenderTableRowBlock {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected table_row object, got ${typeof raw}`);
  }
  const kind = asString(raw.kind, `${path}.kind`);
  if (kind !== 'table_row') {
    throw new InvalidRenderPageError(`${path}.kind`, `expected "table_row", got "${kind}"`);
  }
  const cellsRaw = asArray(raw.cells ?? [], `${path}.cells`);
  return {
    kind: 'table_row',
    id: asString(raw.id, `${path}.id`),
    header: asBoolean(raw.header, `${path}.header`, false),
    cells: cellsRaw.map((cell, i) =>
      normalizeTableCell(cell, `${path}.cells[${i}]`, normalizeInline),
    ),
  };
}

function normalizeTableChild(
  raw: unknown,
  path: string,
  normalizeInline: InlineNormalizer,
): RenderTableChild {
  if (!isObject(raw)) {
    throw new InvalidRenderPageError(path, `expected table child object, got ${typeof raw}`);
  }
  const kind = asString(raw.kind, `${path}.kind`);
  if (kind === 'table_row') {
    return normalizeTableRow(raw, path, normalizeInline);
  }
  return normalizeInline(raw, path);
}

export function normalizeTableChildren(
  raw: unknown,
  path: string,
  normalizeInline: InlineNormalizer,
): RenderTableChild[] {
  return asArray(raw, path).map((child, i) =>
    normalizeTableChild(child, `${path}[${i}]`, normalizeInline),
  );
}
