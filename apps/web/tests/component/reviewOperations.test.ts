import { describe, it, expect } from 'vitest';
import {
  buildReorderOp,
  buildSuppressOp,
  buildTextOp,
  moveBlock,
} from '../../src/lib/review/operations';

describe('review operation builders', () => {
  it('buildTextOp → replace at the text pointer with scope text', () => {
    const op = buildTextOp(1, 0, 'corrected');
    expect(op.op).toBe('replace');
    expect(op.path).toBe('/blocks/1/children/0/text');
    expect(op.value).toBe('corrected');
    expect(op.scope).toBe('text');
  });

  it('buildSuppressOp → delete at the block pointer with scope block_structure', () => {
    const op = buildSuppressOp(3);
    expect(op.op).toBe('delete');
    expect(op.path).toBe('/blocks/3');
    expect(op.scope).toBe('block_structure');
  });

  it('moveBlock swaps with the earlier / later neighbor', () => {
    expect(moveBlock(['a', 'b', 'c'], 1, 'earlier')).toEqual(['b', 'a', 'c']);
    expect(moveBlock(['a', 'b', 'c'], 1, 'later')).toEqual(['a', 'c', 'b']);
  });

  it('moveBlock at an edge returns an unchanged copy (not the same reference)', () => {
    const arr = ['a', 'b'];
    const out = moveBlock(arr, 0, 'earlier');
    expect(out).toEqual(['a', 'b']);
    expect(out).not.toBe(arr);
  });

  it('buildReorderOp → replace /blocks with the reordered raw blocks, scope reading_order', () => {
    const op = buildReorderOp(['a', 'b', 'c'], 2, 'earlier');
    expect(op.op).toBe('replace');
    expect(op.path).toBe('/blocks');
    expect(op.scope).toBe('reading_order');
    expect(op.value).toEqual(['a', 'c', 'b']);
  });
});
