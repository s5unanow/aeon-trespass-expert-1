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
      // Only respond to ru edition manifests for this test
      if (!urlStr.includes('/ru/')) {
        return Promise.resolve({ ok: false, status: 404 } as Response);
      }
      const id = urlStr.includes('ato_core') ? 'ato_core_v1_1' : 'walking_skeleton';
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            document_id: id,
            pages: [{ page_id: 'p0001', title: 'Page 1' }],
          }),
      } as Response);
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
      if (urlStr.includes('walking_skeleton') && urlStr.includes('/ru/')) {
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
});
