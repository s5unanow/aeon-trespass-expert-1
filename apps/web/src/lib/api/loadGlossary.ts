import type { GlossaryPayloadV1 } from '@atr/schemas';

/**
 * Module-level promise cache keyed by `${documentId}:${edition}`.
 *
 * The glossary bundle (~213 KB for `ato_core_v1_1/ru`) is per-document/edition
 * and immutable for the lifetime of a reader session, so the first fetch is
 * shared across every component that needs it (the lifted `GlossaryProvider`,
 * `GlossaryPage`, future consumers). A *rejected* load is evicted before the
 * error propagates, so a transient network failure does not poison the cache —
 * the next caller retries with a fresh fetch.
 */
const glossaryCache = new Map<string, Promise<GlossaryPayloadV1>>();

async function fetchGlossary(documentId: string, edition: string): Promise<GlossaryPayloadV1> {
  const url = `/documents/${documentId}/${edition}/data/glossary.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load glossary: ${res.status} ${url}`);
  }
  return res.json();
}

export function loadGlossary(
  documentId: string,
  edition: string = 'ru',
): Promise<GlossaryPayloadV1> {
  const key = `${documentId}:${edition}`;
  const cached = glossaryCache.get(key);
  if (cached) return cached;

  const promise = fetchGlossary(documentId, edition).catch((err: unknown) => {
    // Evict the failed entry so a retry refetches rather than re-throwing a
    // cached rejection forever.
    glossaryCache.delete(key);
    throw err;
  });
  glossaryCache.set(key, promise);
  return promise;
}

/** Test-only: reset the module-level cache between cases. */
export function clearGlossaryCache(): void {
  glossaryCache.clear();
}
