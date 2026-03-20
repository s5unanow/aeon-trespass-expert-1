import { describe, expect, it, vi, afterEach } from 'vitest';
import { loadManifest } from '../../src/lib/api/loadManifest';

describe('loadManifest', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('returns manifest from edition path when available', async () => {
    const manifest = { document_id: 'doc1', pages: [{ page_id: 'p0001', title: 'Page 1' }] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(manifest) } as Response);

    const result = await loadManifest('doc1');
    expect(result).toEqual(manifest);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/ru/manifest.json');
  });

  it('falls back to root path when edition path 404s', async () => {
    const manifest = { document_id: 'doc1', pages: [{ page_id: 'p0001', title: 'Page 1' }] };
    fetchSpy
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(manifest) } as Response);

    const result = await loadManifest('doc1');
    expect(result).toEqual(manifest);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/ru/manifest.json');
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/manifest.json');
  });

  it('throws when both paths fail', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);

    await expect(loadManifest('missing')).rejects.toThrow(
      'Failed to load manifest: 404 /documents/missing/manifest.json',
    );
  });

  it('throws on network failure', async () => {
    fetchSpy.mockRejectedValue(new TypeError('network error'));

    await expect(loadManifest('doc1')).rejects.toThrow('network error');
  });
});
