import type { QAMetricsV1 } from '@atr/schemas';

/**
 * Fetches the optional ``qa_metrics.json`` published by
 * ``scripts/_export_qa.py`` (S5U-597 / S5U-874).
 *
 * The metrics artifact is **optional** in the bundle: older runs predating
 * metrics emission, or editions whose QA stage emitted no metrics, ship
 * without it (e.g. the RU edition today carries only ``qa_summary.json`` +
 * ``qa_records.json``). The reader must degrade gracefully when it is
 * absent, so a 404 resolves to ``null`` rather than throwing. Only a genuine
 * transport / server error (non-404) is surfaced as a rejection — and even
 * that is treated as "metrics unavailable" by the dashboard, never a hard
 * failure of the findings table.
 */
export async function loadQaMetrics(
  documentId: string,
  edition: string = 'ru',
  signal?: AbortSignal,
): Promise<QAMetricsV1 | null> {
  const url = `/documents/${documentId}/${edition}/data/qa_metrics.json`;
  const res = await fetch(url, { signal });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Failed to load QA metrics: ${res.status}`);
  }
  return (await res.json()) as QAMetricsV1;
}
