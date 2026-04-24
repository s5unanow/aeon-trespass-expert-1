/**
 * Primitive parse/assert helpers shared by `normalize.ts` and
 * `normalize_table.ts`. Extracted to keep each normalizer under the
 * 400-line file-length cap (S5U-704).
 */

/** Thrown when a `render_page.v1` payload cannot be normalized. */
export class InvalidRenderPageError extends Error {
  readonly path: string;
  constructor(path: string, detail: string) {
    super(`Invalid render_page payload at ${path}: ${detail}`);
    this.name = 'InvalidRenderPageError';
    this.path = path;
  }
}

export function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function asArray(v: unknown, path: string): unknown[] {
  if (v === undefined) return [];
  if (!Array.isArray(v)) {
    throw new InvalidRenderPageError(path, `expected array, got ${typeof v}`);
  }
  return v;
}

export function asString(v: unknown, path: string, fallback?: string): string {
  if (v === undefined || v === null) {
    if (fallback !== undefined) return fallback;
    throw new InvalidRenderPageError(path, 'missing required string');
  }
  if (typeof v !== 'string') {
    throw new InvalidRenderPageError(path, `expected string, got ${typeof v}`);
  }
  return v;
}

export function asStringArray(v: unknown, path: string): string[] {
  const arr = asArray(v, path);
  return arr.map((item, i) => asString(item, `${path}[${i}]`));
}

export function asNumber(v: unknown, path: string, fallback: number): number {
  if (v === undefined || v === null) return fallback;
  if (typeof v !== 'number' || Number.isNaN(v)) {
    throw new InvalidRenderPageError(path, `expected number, got ${typeof v}`);
  }
  return v;
}

export function asBoolean(v: unknown, path: string, fallback: boolean): boolean {
  if (v === undefined || v === null) return fallback;
  if (typeof v !== 'boolean') {
    throw new InvalidRenderPageError(path, `expected boolean, got ${typeof v}`);
  }
  return v;
}
