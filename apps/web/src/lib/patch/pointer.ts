// JSON Pointer builders and operation factories for PatchSetV1 targeting render_page.
// All paths target the structure of a normalized render_page.{pageId}.json.
// Client guards live here too (out-of-bounds, empty ops).

import type { PatchOp, PatchScope } from './schema';

/** Build a JSON Pointer into /blocks for a block index. */
export function blockPath(blockIndex: number): string {
  if (!Number.isInteger(blockIndex) || blockIndex < 0) {
    throw new Error(`Invalid block index: ${blockIndex}`);
  }
  return `/blocks/${blockIndex}`;
}

/** Build a JSON Pointer to a specific inline child's text (for text scope corrections). */
export function inlineTextPath(blockIndex: number, childIndex: number): string {
  if (!Number.isInteger(blockIndex) || blockIndex < 0) {
    throw new Error(`Invalid block index: ${blockIndex}`);
  }
  if (!Number.isInteger(childIndex) || childIndex < 0) {
    throw new Error(`Invalid child index: ${childIndex}`);
  }
  return `/blocks/${blockIndex}/children/${childIndex}/text`;
}

/** Create a text-correction replace op. */
export function createTextCorrectionOp(
  blockIndex: number,
  childIndex: number,
  correctedText: string,
): PatchOp {
  if (!correctedText || typeof correctedText !== 'string') {
    throw new Error('correctedText must be a non-empty string');
  }
  return {
    op: 'replace',
    path: inlineTextPath(blockIndex, childIndex),
    value: correctedText,
    scope: 'text' as PatchScope,
  };
}

/** Create a block delete op (for block_structure suppress). */
export function createBlockSuppressOp(blockIndex: number): PatchOp {
  return {
    op: 'delete',
    path: blockPath(blockIndex),
    value: null,
    scope: 'block_structure' as PatchScope,
  };
}

/**
 * Create ops to move a block from fromIndex to toIndex (reading_order).
 * Uses delete + insert to simulate a move using only supported ops.
 * Returns the ops in an order that is safe to apply sequentially (higher indices first for deletes).
 */
export function createReadingOrderOps(
  fromIndex: number,
  toIndex: number,
  blockCount: number,
): PatchOp[] {
  if (
    !Number.isInteger(fromIndex) ||
    !Number.isInteger(toIndex) ||
    fromIndex < 0 ||
    toIndex < 0 ||
    fromIndex >= blockCount ||
    toIndex >= blockCount
  ) {
    throw new Error(`Out of bounds reorder: from=${fromIndex} to=${toIndex} count=${blockCount}`);
  }
  if (fromIndex === toIndex) return [];

  // We will produce a delete at the original location and an insert at the target.
  // Because delete shifts indices, compute the adjusted insert after delete.
  // Safer approach used by auto-fix: process deletes high-to-low.
  // For a single move, delete first (original from), then insert at (possibly adjusted) position.
  const ops: PatchOp[] = [];

  // Represent the "value" being moved as a sentinel; real impl would snapshot the block object.
  // For review MVP the caller is expected to only use this for order intent; the actual
  // value for insert is typically reconstructed by the applicator consumer or omitted
  // for pure order signaling in early drafts. To keep patches valid we insert a minimal
  // placeholder object that downstream can recognize or we use replace on a wrapper.
  //
  // Better practical approach for render_page (array of heterogeneous blocks):
  // 1. Capture the block value at from (but we don't have it here — pointer layer is pure).
  // For this layer we emit the structural ops; the ReviewPage will supply a shallow copy of
  // the block when building the final op list.
  //
  // To keep the function pure and testable, return descriptor ops. The consumer (drawer)
  // will enrich the insert with the actual block value.
  // For simplicity in unit surface we emit:
  // - delete at from
  // - insert at computed target (if to < from then to stays, else to-1 after delete)

  const deleteOp: PatchOp = {
    op: 'delete',
    path: blockPath(fromIndex),
    value: null,
    scope: 'reading_order' as PatchScope,
  };
  ops.push(deleteOp);

  // After delete, indices after from shift left by 1.
  let insertAt = toIndex;
  if (toIndex > fromIndex) {
    insertAt = toIndex - 1;
  }
  // The insert value is intentionally left for the caller to fill with the real block shape.
  // We emit a placeholder marker value here; tests assert shape not exact content.
  const insertOp: PatchOp = {
    op: 'insert',
    path: blockPath(insertAt),
    value: { __patch_move_marker: true, from: fromIndex, to: toIndex },
    scope: 'reading_order' as PatchScope,
  };
  ops.push(insertOp);

  return ops;
}

/** Guard: return true if all ops use valid indices for a page with N blocks (best-effort). */
export function opsAreInBounds(ops: PatchOp[], blockCount: number): boolean {
  for (const op of ops) {
    const m = op.path.match(/^\/blocks\/(\d+)/);
    if (!m) continue;
    const idx = parseInt(m[1], 10);
    if (idx < 0 || idx >= blockCount) return false;
    if (op.op === 'insert') {
      // insert can target up to blockCount (append) or inside
      if (idx > blockCount) return false;
    }
  }
  return true;
}

/** Guard: true only when there is >=1 op and required metadata present. */
export function isExportablePatch(patch: { operations: PatchOp[]; reason?: string; author?: string }): boolean {
  if (!patch.operations || patch.operations.length === 0) return false;
  if (!patch.reason || patch.reason.trim() === '') return false;
  if (!patch.author || patch.author.trim() === '') return false;
  return true;
}
