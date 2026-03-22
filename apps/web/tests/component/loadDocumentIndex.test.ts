import { afterEach, describe, expect, it, vi } from 'vitest';
import { loadDocumentIndex } from '../../src/lib/api/loadDocumentIndex';

describe('loadDocumentIndex', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('returns parsed index when available', async () => {
    const index = {
      documents: [{ document_id: 'doc1', editions: ['en', 'ru'] }],
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(index),
    } as Response);

    const result = await loadDocumentIndex();
    expect(result).toEqual(index);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/index.json');
  });

  it('returns null on 404', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);

    const result = await loadDocumentIndex();
    expect(result).toBeNull();
  });

  it('returns null on network error', async () => {
    fetchSpy.mockRejectedValue(new TypeError('network error'));

    const result = await loadDocumentIndex();
    expect(result).toBeNull();
  });
});
