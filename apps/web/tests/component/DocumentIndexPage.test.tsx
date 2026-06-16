import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router';
import { DocumentIndexPage } from '../../src/routes/DocumentIndexPage';

// DocumentIndexPage now renders router <Link> page pills, so it must mount
// inside a router context (S5U-1225).
function renderIndex() {
  return render(
    <MemoryRouter>
      <DocumentIndexPage />
    </MemoryRouter>,
  );
}

describe('DocumentIndexPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('renders document cards from manifests', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('ato_core') && !urlStr.includes('/ru/') && !urlStr.includes('/en/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'ato_core_v1_1',
              pages: [{ page_id: 'p0001', title: 'Page 1' }],
            }),
        } as Response);
      }
      if (
        urlStr.includes('walking_skeleton') &&
        !urlStr.includes('/ru/') &&
        !urlStr.includes('/en/')
      ) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'walking_skeleton',
              pages: [{ page_id: 'p0001', title: 'Page 1' }],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByText('Walking Skeleton')).toBeDefined();
    });
    expect(screen.getByText('Ato Core v1.1')).toBeDefined();
  });

  it('filters out failed manifest fetches', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('walking_skeleton') && !urlStr.includes('/en/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'walking_skeleton',
              pages: [{ page_id: 'p0001', title: 'OK' }],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getAllByText('Walking Skeleton').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByText(/Ato Core/)).toBeNull();
  });

  it('shows empty state (not an error) when discovery succeeds but every manifest 404s', async () => {
    // All manifest fetches fail individually (caught per-doc); discovery itself
    // succeeded, so this is a legitimate "No documents found", not an error.
    fetchSpy.mockResolvedValue({ ok: false, status: 500 } as Response);

    renderIndex();

    await waitFor(() => {
      expect(screen.getByText('No documents found')).toBeDefined();
    });
    expect(screen.getByText('Aeon Trespass')).toBeDefined();
    // The distinct error alert must NOT appear for an empty-but-successful load.
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows a distinct error alert (not the empty state) when document discovery fails', async () => {
    // A malformed index whose `editions` is not iterable makes discoverDocuments
    // throw, which the outer .catch surfaces as the error state — distinct from
    // a successful-but-empty result.
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.endsWith('/documents/index.json')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ documents: [{ document_id: 'broken', editions: null }] }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });
    expect(screen.getByRole('alert').textContent).toMatch(/could not load/i);
    expect(screen.queryByText('No documents found')).toBeNull();
  });

  it('shows both editions when manifests are edition-specific', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('ato_core') && urlStr.includes('/ru/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'ato_core_v1_1',
              pages: [{ page_id: 'p0001', title: 'RU Page' }],
            }),
        } as Response);
      }
      if (urlStr.includes('ato_core') && urlStr.includes('/en/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'ato_core_v1_1',
              pages: [{ page_id: 'p0001', title: 'EN Page' }],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getAllByText('Ato Core v1.1')).toHaveLength(2);
    });
    expect(screen.getByText('RU')).toBeDefined();
    expect(screen.getByText('EN')).toBeDefined();
  });

  it('uses index.json when available instead of hardcoded list', async () => {
    const index = {
      documents: [{ document_id: 'custom_doc', editions: ['en'] }],
    };
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.endsWith('/documents/index.json')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(index),
        } as Response);
      }
      if (urlStr.includes('custom_doc') && urlStr.includes('/en/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'custom_doc',
              pages: [{ page_id: 'p0001', title: 'Dynamic' }],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByText('Custom Doc')).toBeDefined();
    });
    expect(screen.queryByText(/Ato Core/)).toBeNull();
    expect(screen.queryByText(/Walking Skeleton/)).toBeNull();
  });

  it('renders page pills with formatted numbers', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('walking_skeleton') && urlStr.includes('/ru/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'walking_skeleton',
              pages: [
                { page_id: 'p0001', title: 'First' },
                { page_id: 'p0049', title: 'Forty-Nine' },
              ],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByTitle('First')).toBeDefined();
    });
    expect(screen.getByTitle('First').textContent).toBe('1');
    expect(screen.getByTitle('Forty-Nine').textContent).toBe('49');
  });

  it('renders page pills as client-side router links (relative href, no full reload)', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('walking_skeleton') && urlStr.includes('/ru/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'walking_skeleton',
              pages: [{ page_id: 'p0001', title: 'First' }],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByTitle('First')).toBeDefined();
    });
    const pill = screen.getByTitle('First');
    // react-router <Link> renders an <a> whose href is the in-app route.
    expect(pill.tagName).toBe('A');
    expect(pill.getAttribute('href')).toBe('/documents/walking_skeleton/ru/p0001');
  });

  it('shows page count in card metadata', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      if (urlStr.includes('walking_skeleton') && urlStr.includes('/ru/')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              document_id: 'walking_skeleton',
              pages: [
                { page_id: 'p0001', title: 'A' },
                { page_id: 'p0002', title: 'B' },
                { page_id: 'p0003', title: 'C' },
              ],
            }),
        } as Response);
      }
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });

    renderIndex();

    await waitFor(() => {
      expect(screen.getByText('3 pages')).toBeDefined();
    });
  });

  it('shows loading skeleton before manifests resolve', () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));

    renderIndex();

    expect(screen.getByLabelText('Loading documents')).toBeDefined();
    expect(screen.getByLabelText('Loading documents').getAttribute('aria-busy')).toBe('true');
  });
});
