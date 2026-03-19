import { describe, expect, it, vi, afterEach } from 'vitest';
import { loadRenderPage } from '../../src/lib/api/loadRenderPage';

describe('loadRenderPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('returns page data on success', async () => {
    const data = { schema_version: 'render_page.v1', page: { id: 'p0001' }, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    const result = await loadRenderPage('doc1', 'p0001');
    expect(result).toEqual(data);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/data/render_page.p0001.json');
  });

  it('throws on HTTP error', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow('Failed to load render page: 500');
  });

  it('throws on missing schema_version', async () => {
    const data = { page: { id: 'p0001' }, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow('Invalid render page data for p0001');
  });

  it('throws on missing page field', async () => {
    const data = { schema_version: 'render_page.v1', blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow('Invalid render page data for p0001');
  });

  it('throws on network failure', async () => {
    fetchSpy.mockRejectedValue(new TypeError('network error'));

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow('network error');
  });
});
