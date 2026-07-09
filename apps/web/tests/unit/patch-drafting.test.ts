/**
 * Vitest unit tests for S5U-1538 patch drafting helpers.
 *
 * Covers:
 * - JSON pointer path building (text, block)
 * - Ordering op construction + bounds
 * - Export shape guards (reason + author required)
 * - Roundtrip construction that matches generated TS shape at compile time.
 *
 * Red-before evidence will be recorded in the commit that introduces each new `it`.
 */
import { describe, it, expect } from 'vitest';

import {
  blockPath,
  inlineTextPath,
  createTextCorrectionOp,
  createBlockSuppressOp,
  createReadingOrderOps,
  opsAreInBounds,
  isExportablePatch,
} from '../../src/lib/patch/pointer';
import type { PatchOp } from '../../src/lib/patch/schema';
import { createEmptyPatchSet } from '../../src/lib/patch/schema';

describe('patch pointer builders (S5U-1538)', () => {
  it('blockPath produces /blocks/N for valid index', () => {
    expect(blockPath(0)).toBe('/blocks/0');
    expect(blockPath(5)).toBe('/blocks/5');
  });

  it('inlineTextPath produces /blocks/N/children/M/text', () => {
    expect(inlineTextPath(2, 1)).toBe('/blocks/2/children/1/text');
  });

  it('rejects negative indices', () => {
    expect(() => blockPath(-1)).toThrow(/Invalid block index/);
    expect(() => inlineTextPath(0, -3)).toThrow(/Invalid child index/);
  });
});

describe('patch operation factories (S5U-1538)', () => {
  it('createTextCorrectionOp yields replace with scope text and correct path', () => {
    const op = createTextCorrectionOp(0, 0, 'Corrected text here');
    expect(op.op).toBe('replace');
    expect(op.path).toBe('/blocks/0/children/0/text');
    expect(op.value).toBe('Corrected text here');
    expect(op.scope).toBe('text');
  });

  it('createBlockSuppressOp yields delete with scope block_structure', () => {
    const op = createBlockSuppressOp(3);
    expect(op.op).toBe('delete');
    expect(op.path).toBe('/blocks/3');
    expect(op.scope).toBe('block_structure');
  });

  it('createReadingOrderOps produces delete + insert pair with reading_order scope', () => {
    const ops = createReadingOrderOps(2, 0, 5);
    expect(ops).toHaveLength(2);
    expect(ops[0].op).toBe('delete');
    expect(ops[0].scope).toBe('reading_order');
    expect(ops[1].op).toBe('insert');
    expect(ops[1].scope).toBe('reading_order');
    // Path computation: moving 2 -> 0 should delete /blocks/2 then insert at 0
    expect(ops[0].path).toBe('/blocks/2');
    expect(ops[1].path).toBe('/blocks/0');
  });

  it('createReadingOrderOps returns [] for no-op same index', () => {
    expect(createReadingOrderOps(2, 2, 5)).toEqual([]);
  });

  it('rejects out-of-bounds reorder', () => {
    expect(() => createReadingOrderOps(10, 0, 3)).toThrow(/Out of bounds/);
  });
});

describe('client guards (S5U-1538)', () => {
  it('opsAreInBounds rejects out-of-range block index', () => {
    const bad: PatchOp[] = [{ op: 'replace', path: '/blocks/9/children/0/text', value: 'x', scope: 'text' }];
    expect(opsAreInBounds(bad, 4)).toBe(false);
    const good: PatchOp[] = [{ op: 'replace', path: '/blocks/1/children/0/text', value: 'x', scope: 'text' }];
    expect(opsAreInBounds(good, 4)).toBe(true);
  });

  it('isExportablePatch requires non-empty ops + reason + author', () => {
    const empty = createEmptyPatchSet({ documentId: 'd', edition: 'en', pageId: 'p1' });
    expect(isExportablePatch(empty)).toBe(false);

    const withOps = { ...empty, operations: [{ op: 'delete', path: '/blocks/0', scope: 'block_structure' } as PatchOp] };
    expect(isExportablePatch(withOps)).toBe(false); // still missing reason/author

    const ready = { ...withOps, reason: 'Fix reading order', author: 'reviewer@example' };
    expect(isExportablePatch(ready)).toBe(true);
  });
});

describe('PatchSetV1 construction shape (compile + runtime, S5U-1538)', () => {
  it('createEmptyPatchSet produces a value assignable to generated PatchSetV1', () => {
    const p = createEmptyPatchSet({ documentId: 'ato_core_v1_1', edition: 'en', pageId: 'p0015', author: 's5u' });
    // Compile-time: the import type already enforces this.
    // Runtime shape spot-checks:
    expect(p.schema_version).toBe('patch_set.v1');
    expect(p.target_kind).toBe('render_page');
    expect(Array.isArray(p.operations)).toBe(true);
    expect(typeof p.patch_id).toBe('string');
    expect(p.patch_id).toContain('review-');
  });
});
