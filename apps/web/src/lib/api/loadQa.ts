import type { QARecordV1, QASummaryV1 } from '@atr/schemas';

/** Wrapper around the exported ``qa_records.json`` bundle. */
export interface QaRecordsFile {
  records: QARecordV1[];
}

export interface QaBundle {
  summary: QASummaryV1;
  records: QARecordV1[];
}

/**
 * Fetches the QA summary + records published by ``scripts/export_to_web.py``.
 * Both files live next to ``glossary.json`` under ``<edition>/data/``.
 */
export async function loadQa(
  documentId: string,
  edition: string = 'ru',
  signal?: AbortSignal,
): Promise<QaBundle> {
  const base = `/documents/${documentId}/${edition}/data`;
  const [summaryRes, recordsRes] = await Promise.all([
    fetch(`${base}/qa_summary.json`, { signal }),
    fetch(`${base}/qa_records.json`, { signal }),
  ]);
  if (!summaryRes.ok) {
    throw new Error(`Failed to load QA summary: ${summaryRes.status}`);
  }
  if (!recordsRes.ok) {
    throw new Error(`Failed to load QA records: ${recordsRes.status}`);
  }
  const summary: QASummaryV1 = await summaryRes.json();
  const recordsFile: QaRecordsFile = await recordsRes.json();
  return { summary, records: recordsFile.records ?? [] };
}
