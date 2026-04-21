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
  const summary: PublicQASummaryV1 = await summaryRes.json();
  const recordsFile: QaRecordsFile = await recordsRes.json();
  return { summary, records: recordsFile.records ?? [] };
}
