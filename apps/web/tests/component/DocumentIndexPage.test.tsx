import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { DocumentIndexPage } from '../../src/routes/DocumentIndexPage';

describe('DocumentIndexPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('renders document sections from manifests', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      // Respond to root-path fallback for both docs
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

    render(<DocumentIndexPage />);

    await waitFor(() => {
      expect(screen.getByText('walking_skeleton (RU)')).toBeDefined();
    });
    expect(screen.getByText('ato_core_v1_1 (RU)')).toBeDefined();
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

    render(<DocumentIndexPage />);

    await waitFor(() => {
      expect(screen.getByText('walking_skeleton (RU)')).toBeDefined();
    });
    expect(screen.queryByText('ato_core_v1_1')).toBeNull();
  });

  it('renders empty when all manifests fail', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 500 } as Response);

    render(<DocumentIndexPage />);

    await waitFor(() => {
      expect(screen.getByText('Aeon Trespass — Rules Reader')).toBeDefined();
    });
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('shows both editions when manifests are edition-specific', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      // Edition-specific manifests for ato_core
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

    render(<DocumentIndexPage />);

    await waitFor(() => {
      expect(screen.getByText('ato_core_v1_1 (RU)')).toBeDefined();
    });
    // Both editions should be visible since they resolved to edition-specific paths
    expect(screen.getByText('ato_core_v1_1 (EN)')).toBeDefined();
  });

  it('formats page numbers without leading zeros', async () => {
    fetchSpy.mockImplementation((url) => {
      const urlStr = String(url);
      // Only respond to ru edition of walking_skeleton
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

    render(<DocumentIndexPage />);

    await waitFor(() => {
      expect(screen.getByText(/^1 — First$/)).toBeDefined();
    });
    expect(screen.getByText(/^49 — Forty-Nine$/)).toBeDefined();
  });
});
