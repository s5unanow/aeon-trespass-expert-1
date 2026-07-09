/**
 * Builders that turn a reviewer's intent into a generated `PatchOperation`.
 *
 * Every operation is a single RFC-6901 patch that the pipeline-side
 * `apply_patches` applicator (`replace` / `insert` / `delete`) applies to the
 * `render_page.{pageId}.json` artifact, leaving a document that still validates
 * as `RenderPageV1`. Shapes come only from the generated `@atr/schemas` types.
 */

import type { patchSetV1 } from '@atr/schemas';
import { blockPointer, blockTextPointer, blocksPointer } from './pointer';

export type PatchOperation = patchSetV1.PatchOperation;
/** Full generated scope enum (8 values). */
export type PatchScope = NonNullable<patchSetV1.PatchOperation['scope']>;
/** The subset of scopes the MVP review UI can draft; assignable to PatchScope. */
export type ReviewScope = Extract<PatchScope, 'text' | 'reading_order' | 'block_structure'>;

/** Move a block one position earlier (up) or later (down) in reading order. */
export type ReorderDirection = 'earlier' | 'later';

/**
 * `PatchOperation.value` is schema-untyped (Pydantic `object`), so the
 * generated `Value` type is an open record. Concrete correction values are a
 * string (text edit) or a block array (reorder); this localized cast is the one
 * place we bridge them into the generated slot without inventing a patch shape.
 */
export function asPatchValue(value: unknown): patchSetV1.PatchOperation['value'] {
  return value as patchSetV1.PatchOperation['value'];
}

/** scope=text — replace the `text` of a text inline inside a block. */
export function buildTextOp(
  blockIndex: number,
  inlineIndex: number,
  newText: string,
): PatchOperation {
  return {
    op: 'replace',
    path: blockTextPointer(blockIndex, inlineIndex),
    value: asPatchValue(newText),
    scope: 'text',
  };
}

/** scope=block_structure — suppress (delete) a block from the page. */
export function buildSuppressOp(blockIndex: number): PatchOperation {
  return {
    op: 'delete',
    path: blockPointer(blockIndex),
    value: asPatchValue(null),
    scope: 'block_structure',
  };
}

/**
 * Pure reorder: return a copy of `arr` with the element at `index` moved one
 * slot `earlier`/`later`. At an edge the element cannot move, so a shallow copy
 * is returned unchanged (callers should disable the control at the boundary).
 */
export function moveBlock<T>(arr: readonly T[], index: number, direction: ReorderDirection): T[] {
  const next = [...arr];
  const target = direction === 'earlier' ? index - 1 : index + 1;
  if (index < 0 || index >= next.length || target < 0 || target >= next.length) {
    return next;
  }
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/**
 * scope=reading_order — replace the whole ordered `/blocks` array with the
 * block at `blockIndex` moved one position. A single `replace` op keeps the
 * result a valid `RenderPageV1`. It operates on the **raw** loaded blocks so
 * the round-trip is a faithful reorder (no re-materialized default fields).
 *
 * NOTE (MVP): because JSON pointers are index-based, this whole-array replace
 * is a coarse, standalone edit and does not compose with index-targeted `text`
 * / `block_structure` ops in the same patch set — see plan-s5u-1539.md.
 */
export function buildReorderOp(
  rawBlocks: readonly unknown[],
  blockIndex: number,
  direction: ReorderDirection,
): PatchOperation {
  return {
    op: 'replace',
    path: blocksPointer(),
    value: asPatchValue(moveBlock(rawBlocks, blockIndex, direction)),
    scope: 'reading_order',
  };
}
