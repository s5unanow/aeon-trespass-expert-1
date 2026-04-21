import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadQa } from '../../src/lib/api/loadQa';

describe('loadQa', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('fetches summary and records and returns a bundle', async () => {
    // Mocks match the public DTO shapes (PublicQASummaryV1 / PublicQARecordSetV1)
    // written by scripts/_export_qa.py. The web boundary no longer sees
    // run_id / record_refs / per-record schema_version / document_id.
    const summary = {
      schema_version: 'public_qa_summary.v1',
      document_id: 'test_doc',
      edition: 'ru',
      counts: { info: 0, warning: 1, error: 0, critical: 0 },
      waived_counts: { info: 0, warning: 0, error: 0, critical: 0 },
      blocking: false,
    };
    const records = {
      schema_version: 'public_qa_record_set.v1',
      records: [
        {
          qa_id: 'qa.a',
          layer: 'structure',
          severity: 'warning',
          code: 'C',
          page_id: 'p0003',
          message: 'msg',
        },
      ],
    };
    fetchSpy.mockImplementation((url: RequestInfo | URL) => {
      const u = String(url);
      if (u.endsWith('qa_summary.json')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) } as Response);
      }
      if (u.endsWith('qa_records.json')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(records) } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    const bundle = await loadQa('test_doc', 'ru');
    expect(bundle.summary.document_id).toBe('test_doc');
    expect(bundle.records).toHaveLength(1);
    expect(bundle.records[0].qa_id).toBe('qa.a');
  });

  it('throws when summary fetch fails', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);
    await expect(loadQa('missing', 'ru')).rejects.toThrow(/QA summary/);
  });

  it('handles missing records array gracefully', async () => {
    fetchSpy.mockImplementation((url: RequestInfo | URL) => {
      const u = String(url);
      if (u.endsWith('qa_summary.json')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ document_id: 'd' }),
        } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    });
    const bundle = await loadQa('d', 'ru');
    expect(bundle.records).toEqual([]);
  });
});
