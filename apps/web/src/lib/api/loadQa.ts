import type { PublicQARecordSetV1, PublicQASummaryV1, publicQaRecordSetV1 } from '@atr/schemas';

/**
 * Wrapper around the exported ``qa_records.json`` bundle.
 *
 * The public projection (S5U-689) ships ``PublicQARecordSetV1`` shape;
 * this alias keeps downstream callers happy while the types are generated
 * directly from the Pydantic public DTO.
 */
export type QaRecordsFile = PublicQARecordSetV1;

export interface QaBundle {
  summary: PublicQASummaryV1;
  records: publicQaRecordSetV1.PublicQARecordV1[];
}

/**
 * Module-level promise cache keyed by `${documentId}:${edition}`.
 *
 * The QA bundle (`qa_summary.json` + `qa_records.json`, ~60 KB) is
 * per-document/edition — only the derived per-page count differs between
 * reader pages. Caching the shared promise means `QaPageBadge` (one mount per
 * page turn) and `QaDashboard` fetch the bundle exactly once per session.
 *
 * The `signal` parameter is intentionally dropped from the cached fetch: a
 * shared promise cannot be aborted on behalf of one caller without breaking
 * every other awaiter, and callers already guard `setState` behind a `stale`
 * flag, so abort was only ever a network-saving optimization. Callers' existing
 * `AbortController` usage stays harmless (the `signal` arg is accepted and
 * ignored). A *rejected* load is evicted before the error propagates so a
 * transient failure does not poison the cache.
 */
const qaCache = new Map<string, Promise<QaBundle>>();

async function fetchQa(documentId: string, edition: string): Promise<QaBundle> {
  const base = `/documents/${documentId}/${edition}/data`;
  const [summaryRes, recordsRes] = await Promise.all([
    fetch(`${base}/qa_summary.json`),
    fetch(`${base}/qa_records.json`),
  ]);
  if (!summaryRes.ok) {
    throw new Error(`Failed to load QA summary: ${summaryRes.status}`);
  }
  if (!recordsRes.ok) {
    throw new Error(`Failed to load QA records: ${recordsRes.status}`);
  }
  const summary: PublicQASummaryV1 = await summaryRes.json();
  const recordsFile: QaRecordsFile = await recordsRes.json();
  return { summary, records: recordsFile.records ?? [] };
}

/**
 * Fetches the QA summary + records published by ``scripts/export_to_web.py``.
 * Both files live next to ``glossary.json`` under ``<edition>/data/``.
 *
 * `signal` is accepted for backwards compatibility but no longer wired into the
 * shared cached fetch (see the cache comment above).
 */
export function loadQa(
  documentId: string,
  edition: string = 'ru',
  _signal?: AbortSignal,
): Promise<QaBundle> {
  const key = `${documentId}:${edition}`;
  const cached = qaCache.get(key);
  if (cached) return cached;

  const promise = fetchQa(documentId, edition).catch((err: unknown) => {
    qaCache.delete(key);
    throw err;
  });
  qaCache.set(key, promise);
  return promise;
}

/** Test-only: reset the module-level cache between cases. */
export function clearQaCache(): void {
  qaCache.clear();
}
