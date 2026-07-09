/**
 * Shared bbox-overlay geometry helpers.
 *
 * Extracted from `components/reader/FacsimilePage.tsx` (S5U-1539) so the
 * extraction-review overlay (`components/review/BlockOverlay.tsx`) reuses the
 * exact reading-order sort and the S5U-697 smaller-bbox-on-top stacking rule
 * rather than copying it. `FacsimilePage` and `BlockOverlay` both consume these
 * pure functions; behavior is unchanged from the original inline implementation.
 */

/** Bounding box in normalized [0,1] page coordinate space. */
export interface Bbox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Vertical tolerance (fraction of page height) for same-row grouping. */
export const ROW_TOLERANCE = 0.02;

/**
 * Reading-order comparator: top-to-bottom by bbox vertical center, then
 * left-to-right by `x0` within the same row (rows within `tolerance`).
 */
export function readingOrderCompare(a: Bbox, b: Bbox, tolerance: number = ROW_TOLERANCE): number {
  const ay = (a.y0 + a.y1) / 2;
  const by = (b.y0 + b.y1) / 2;
  if (Math.abs(ay - by) > tolerance) return ay - by;
  return a.x0 - b.x0;
}

/**
 * Normalized bbox area (unit square). Smaller-area boxes are more specific
 * hotspots and must paint on top of larger ones — otherwise a large enclosing
 * region silently intercepts clicks meant for an inner marker (S5U-697).
 */
export function bboxArea(bbox: Bbox): number {
  const w = Math.max(0, bbox.x1 - bbox.x0);
  const h = Math.max(0, bbox.y1 - bbox.y0);
  return w * h;
}

/**
 * Assign a stacking rank to each item (in input order) so that smaller bboxes
 * receive a higher rank and therefore paint later / stack higher. Rank 0 is the
 * largest bbox. The returned array is index-aligned with `items`.
 */
export function assignStackRanks(items: readonly { bbox: Bbox }[]): number[] {
  const indexed = items.map((item, i) => ({ i, area: bboxArea(item.bbox) }));
  // Descending area → smallest bbox gets the highest rank.
  indexed.sort((a, b) => b.area - a.area);
  const ranks = Array.from({ length: items.length }, () => 0);
  indexed.forEach((entry, rank) => {
    ranks[entry.i] = rank;
  });
  return ranks;
}
