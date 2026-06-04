import { afterEach, describe, expect, it, vi } from 'vitest';
import type { QAMetricsV1 } from '@atr/schemas';
import { loadQaMetrics } from '../../src/lib/api/loadQaMetrics';

const SAMPLE: QAMetricsV1 = {
  schema_version: 'qa_metrics.v1',
  document_id: 'ato_core_v1_1',
  edition: 'en',
  pages_total: 83,
  pages_with_findings: 83,
  clean_page_rate: 0,
  findings_by_severity: { info: 70, warning: 426, error: 1250, critical: 0 },
  findings_by_layer: { terminology: 1249, render: 370 },
  findings_by_code_top10: [{ code: 'UNTRANSLATED_TEXT', count: 1249 }],
  waived_count: 0,
  blocking_count: 1250,
  avg_findings_per_page: 21.04,
};

describe('loadQaMetrics', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('returns the parsed metrics when the artifact is present', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(SAMPLE),
    } as Response);
    const result = await loadQaMetrics('ato_core_v1_1', 'en');
    expect(result).not.toBeNull();
    expect(result?.blocking_count).toBe(1250);
    expect(result?.document_id).toBe('ato_core_v1_1');
  });

  it('degrades to null when qa_metrics.json is absent (404)', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);
    const result = await loadQaMetrics('ato_core_v1_1', 'ru');
    expect(result).toBeNull();
  });

  it('throws on a non-404 transport error so the caller can decide', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 500 } as Response);
    await expect(loadQaMetrics('ato_core_v1_1', 'en')).rejects.toThrow(/500/);
  });
});
