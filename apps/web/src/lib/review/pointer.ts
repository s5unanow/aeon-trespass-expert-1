/**
 * RFC-6901 JSON-Pointer builders and a resolver for extraction-review patches.
 *
 * Corrections target the loaded `render_page.{pageId}.json` artifact
 * (`target_kind: render_page`). All pointers below address positions inside
 * that document so the pipeline-side `apply_patches` applicator can apply them.
 */

/** Escape a reference token per RFC-6901 (`~` → `~0`, `/` → `~1`). */
function escapeToken(token: string): string {
  return token.replace(/~/g, '~0').replace(/\//g, '~1');
}

/** Pointer to a block's first-level position in `/blocks`. */
export function blockPointer(blockIndex: number): string {
  return `/blocks/${blockIndex}`;
}

/** Pointer to the whole ordered `/blocks` array (reading-order edits). */
export function blocksPointer(): string {
  return '/blocks';
}

/** Pointer to the `text` field of a text inline within a block's children. */
export function blockTextPointer(blockIndex: number, inlineIndex: number): string {
  return `/blocks/${blockIndex}/children/${inlineIndex}/text`;
}

/** Parse a JSON Pointer into unescaped tokens (empty pointer → []). */
export function parsePointer(pointer: string): string[] {
  if (pointer === '') return [];
  if (!pointer.startsWith('/')) {
    throw new Error(`JSON Pointer must start with "/": ${JSON.stringify(pointer)}`);
  }
  return pointer
    .split('/')
    .slice(1)
    .map((t) => t.replace(/~1/g, '/').replace(/~0/g, '~'));
}

/**
 * Resolve a JSON Pointer against `doc`, returning the referenced value.
 * Throws if any token does not resolve — this is the check the unit test uses
 * to prove a drafted pointer actually addresses a node in the render JSON.
 */
export function resolvePointer(doc: unknown, pointer: string): unknown {
  const tokens = parsePointer(pointer);
  let current: unknown = doc;
  for (const token of tokens) {
    if (Array.isArray(current)) {
      const idx = Number(token);
      if (!Number.isInteger(idx) || idx < 0 || idx >= current.length) {
        throw new Error(`Pointer token "${token}" out of range for array at ${pointer}`);
      }
      current = current[idx];
    } else if (current !== null && typeof current === 'object') {
      const rec = current as Record<string, unknown>;
      if (!(token in rec)) {
        throw new Error(`Pointer token "${token}" not found at ${pointer}`);
      }
      current = rec[token];
    } else {
      throw new Error(`Cannot descend into ${typeof current} at token "${token}" (${pointer})`);
    }
  }
  return current;
}

// Re-exported escape helper for callers that build custom tokens.
export { escapeToken };
