import { describe, it, expect } from 'vitest';
import {
  assignStackRanks,
  bboxArea,
  readingOrderCompare,
} from '../../src/lib/render/overlayStacking';

// Guards the S5U-1539 extraction of the S5U-697 stacking logic out of
// FacsimilePage — the shared helpers must preserve the original behavior.

describe('overlayStacking', () => {
  it('bboxArea is width*height (unit square), clamped at 0', () => {
    expect(bboxArea({ x0: 0, y0: 0, x1: 0.5, y1: 0.4 })).toBeCloseTo(0.2);
    expect(bboxArea({ x0: 0.5, y0: 0.5, x1: 0.4, y1: 0.4 })).toBe(0);
  });

  it('readingOrderCompare sorts top-to-bottom then left-to-right', () => {
    const a = { x0: 0.5, y0: 0.0, x1: 0.6, y1: 0.1 }; // higher row
    const b = { x0: 0.1, y0: 0.5, x1: 0.2, y1: 0.6 }; // lower row
    expect(readingOrderCompare(a, b)).toBeLessThan(0);
    // Same row (within tolerance) → left-to-right by x0.
    const l = { x0: 0.1, y0: 0.3, x1: 0.2, y1: 0.31 };
    const r = { x0: 0.7, y0: 0.305, x1: 0.8, y1: 0.315 };
    expect(readingOrderCompare(l, r)).toBeLessThan(0);
  });

  it('assignStackRanks gives smaller bboxes a higher rank (paint on top)', () => {
    const big = { bbox: { x0: 0, y0: 0, x1: 1, y1: 1 } }; // area 1
    const mid = { bbox: { x0: 0, y0: 0, x1: 0.5, y1: 0.5 } }; // area 0.25
    const small = { bbox: { x0: 0, y0: 0, x1: 0.1, y1: 0.1 } }; // area 0.01
    const ranks = assignStackRanks([big, mid, small]);
    // Index-aligned with input; largest area → rank 0.
    expect(ranks[0]).toBe(0);
    expect(ranks[2]).toBeGreaterThan(ranks[1]);
    expect(ranks[1]).toBeGreaterThan(ranks[0]);
  });

  it('assignStackRanks returns index-aligned ranks for any input order', () => {
    const items = [
      { bbox: { x0: 0, y0: 0, x1: 0.2, y1: 0.2 } }, // small
      { bbox: { x0: 0, y0: 0, x1: 1, y1: 1 } }, // big
    ];
    const ranks = assignStackRanks(items);
    expect(ranks[1]).toBe(0); // big → rank 0
    expect(ranks[0]).toBe(1); // small → higher rank
  });
});
