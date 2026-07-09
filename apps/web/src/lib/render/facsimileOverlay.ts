import type { FacsimileAnnotation } from './types';

/** Vertical tolerance (fraction of page height) for same-row grouping. */
const ROW_TOLERANCE = 0.02;

function readingOrder(a: FacsimileAnnotation, b: FacsimileAnnotation): number {
  const ay = (a.bbox.y0 + a.bbox.y1) / 2;
  const by = (b.bbox.y0 + b.bbox.y1) / 2;
  if (Math.abs(ay - by) > ROW_TOLERANCE) return ay - by;
  return a.bbox.x0 - b.bbox.x0;
}

function bboxArea(annotation: FacsimileAnnotation): number {
  const width = Math.max(0, annotation.bbox.x1 - annotation.bbox.x0);
  const height = Math.max(0, annotation.bbox.y1 - annotation.bbox.y0);
  return width * height;
}

export function sortFacsimileAnnotations(
  annotations: readonly FacsimileAnnotation[],
): FacsimileAnnotation[] {
  return [...annotations].sort(readingOrder);
}

/** S5U-697: smaller, more-specific bboxes always stack above larger regions. */
export function facsimileStackRanks(annotations: readonly FacsimileAnnotation[]): number[] {
  const indexed = annotations.map((annotation, index) => ({
    index,
    area: bboxArea(annotation),
  }));
  indexed.sort((a, b) => b.area - a.area);
  const ranks = Array.from({ length: annotations.length }, () => 0);
  indexed.forEach((entry, rank) => {
    ranks[entry.index] = rank;
  });
  return ranks;
}
