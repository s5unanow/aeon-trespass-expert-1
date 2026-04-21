import { describe, expect, it, vi, afterEach } from 'vitest';
import { loadRenderPage } from '../../src/lib/api/loadRenderPage';

describe('loadRenderPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
  });

  it('returns normalized page data from edition path', async () => {
    const data = { schema_version: 'render_page.v1', page: { id: 'p0001' }, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    const result = await loadRenderPage('doc1', 'p0001');
    // Normalizer materializes defaulted fields.
    expect(result.schema_version).toBe('render_page.v1');
    expect(result.page.id).toBe('p0001');
    expect(result.page.title).toBe('');
    expect(result.page.section_path).toEqual([]);
    expect(result.page.source_page_number).toBe(0);
    expect(result.blocks).toEqual([]);
    expect(result.nav).toEqual({ prev: null, next: null, parent_section: '' });
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/ru/data/render_page.p0001.json', {
      signal: undefined,
    });
  });

  it('falls back to root path when edition path 404s', async () => {
    const data = { schema_version: 'render_page.v1', page: { id: 'p0001' }, blocks: [] };
    fetchSpy
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(data) } as Response);

    const result = await loadRenderPage('doc1', 'p0001');
    expect(result.page.id).toBe('p0001');
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/ru/data/render_page.p0001.json', {
      signal: undefined,
    });
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/data/render_page.p0001.json', {
      signal: undefined,
    });
  });

  it('throws when both paths fail with 404', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      'Failed to load render page: 404 /documents/doc1/data/render_page.p0001.json',
    );
  });

  it('throws on 500 from edition path without falling back', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 500 } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      'Edition fetch failed: 500 /documents/doc1/ru/data/render_page.p0001.json',
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('throws on 403 from edition path without falling back', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 403 } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      'Edition fetch failed: 403 /documents/doc1/ru/data/render_page.p0001.json',
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('throws on 502 from edition path without falling back', async () => {
    fetchSpy.mockResolvedValueOnce({ ok: false, status: 502 } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      'Edition fetch failed: 502 /documents/doc1/ru/data/render_page.p0001.json',
    );
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('rejects unsupported schema_version at the fetch boundary', async () => {
    const data = { schema_version: 'render_page.v99', page: { id: 'p0001' }, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      /Invalid render_page payload at schema_version:.*render_page\.v99/,
    );
  });

  it('rejects payload missing page.id', async () => {
    const data = { schema_version: 'render_page.v1', page: {}, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      /Invalid render_page payload at page\.id: missing required string/,
    );
  });

  it('rejects payload whose page field is missing entirely', async () => {
    const data = { schema_version: 'render_page.v1', blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      /Invalid render_page payload at page: expected object/,
    );
  });

  it('rejects payload carrying an unknown block kind', async () => {
    const data = {
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
      blocks: [{ kind: 'mystery', id: 'p0001.b001' }],
    };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      /Invalid render_page payload at blocks\[0\]\.kind: unsupported block kind "mystery"/,
    );
  });

  it('rejects payload carrying an unknown inline kind', async () => {
    const data = {
      schema_version: 'render_page.v1',
      page: { id: 'p0001' },
      blocks: [
        {
          kind: 'paragraph',
          id: 'p0001.b001',
          children: [{ kind: 'hologram', text: '…' }],
        },
      ],
    };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow(
      /blocks\[0\]\.children\[0\]\.kind: unsupported inline kind "hologram"/,
    );
  });

  it('throws on network failure', async () => {
    fetchSpy.mockRejectedValue(new TypeError('network error'));

    await expect(loadRenderPage('doc1', 'p0001')).rejects.toThrow('network error');
  });

  it('passes abort signal to fetch calls', async () => {
    const controller = new AbortController();
    const data = { schema_version: 'render_page.v1', page: { id: 'p0001' }, blocks: [] };
    fetchSpy.mockResolvedValue({ ok: true, json: () => Promise.resolve(data) } as Response);

    await loadRenderPage('doc1', 'p0001', 'ru', controller.signal);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/ru/data/render_page.p0001.json', {
      signal: controller.signal,
    });
  });

  it('passes abort signal to fallback fetch', async () => {
    const controller = new AbortController();
    const data = { schema_version: 'render_page.v1', page: { id: 'p0001' }, blocks: [] };
    fetchSpy
      .mockResolvedValueOnce({ ok: false, status: 404 } as Response)
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(data) } as Response);

    await loadRenderPage('doc1', 'p0001', 'ru', controller.signal);
    expect(fetchSpy).toHaveBeenCalledWith('/documents/doc1/data/render_page.p0001.json', {
      signal: controller.signal,
    });
  });
});
