import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ReaderPage } from '../../src/routes/ReaderPage';
import sampleRenderPage from '../../public/documents/walking_skeleton/data/render_page.p0001.json';
import type { RenderPageData } from '../../src/lib/render/types';

function renderPage(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/documents/:documentId/:edition/:pageId" element={<ReaderPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ReaderPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('renders the walking skeleton page with heading and icon', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleRenderPage),
    } as Response);

    renderPage('/documents/walking_skeleton/ru/p0001');

    await waitFor(() => {
      expect(screen.getByText('Проверка атаки')).toBeDefined();
    });
    expect(screen.getByText('Получите 1')).toBeDefined();
    expect(screen.getByRole('img', { name: 'Прогресс' })).toBeDefined();
    expect(screen.getByText('p.1')).toBeDefined();
  });

  it('shows loading state before data arrives', () => {
    fetchSpy.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage('/documents/walking_skeleton/ru/p0001');
    expect(screen.getByText('Loading...')).toBeDefined();
  });

  it('shows error when fetch fails', async () => {
    fetchSpy.mockRejectedValue(new Error('network down'));
    renderPage('/documents/walking_skeleton/ru/p0001');

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });
    expect(screen.getByRole('alert').textContent).toContain('network down');
  });

  it('renders prev/next navigation links', async () => {
    const pageWithNav = {
      ...sampleRenderPage,
      nav: { prev: 'p0001', next: 'p0003', parent_section: '' },
    };
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(pageWithNav),
    } as Response);

    renderPage('/documents/walking_skeleton/ru/p0002');

    await waitFor(() => {
      expect(screen.getByText(/Prev/)).toBeDefined();
    });
    const prev = screen.getByText(/Prev/).closest('a');
    const next = screen.getByText(/Next/).closest('a');
    expect(prev?.getAttribute('href')).toBe('/documents/walking_skeleton/ru/p0001');
    expect(next?.getAttribute('href')).toBe('/documents/walking_skeleton/ru/p0003');
  });

  it('discards stale responses on rapid navigation', async () => {
    const stalePage = {
      ...sampleRenderPage,
      page: { ...sampleRenderPage.page, id: 'p0001', source_page_number: 99 },
    };
    const freshPage = {
      ...sampleRenderPage,
      page: { ...sampleRenderPage.page, id: 'p0002', source_page_number: 42 },
    };

    // First fetch (p0001) resolves slowly after second fetch (p0002)
    let resolveStale: (v: Response) => void;
    const stalePromise = new Promise<Response>((r) => {
      resolveStale = r;
    });

    fetchSpy.mockReturnValueOnce(stalePromise).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(freshPage),
    } as Response);

    const { unmount } = renderPage('/documents/doc1/ru/p0001');

    // Re-render with new route (simulates rapid navigation)
    unmount();
    renderPage('/documents/doc1/ru/p0002');

    // Fresh page renders with source_page_number 42
    await waitFor(() => {
      expect(screen.getByText('p.42')).toBeDefined();
    });

    // Now resolve the stale request — it should NOT update state
    resolveStale!({
      ok: true,
      json: () => Promise.resolve(stalePage),
    } as Response);

    // Verify the page still shows fresh data (p.42), not stale (p.99)
    await waitFor(() => {
      expect(screen.getByText('p.42')).toBeDefined();
    });
    expect(screen.queryByText('p.99')).toBeNull();
  });

  it('does not set error when request is aborted', async () => {
    fetchSpy.mockRejectedValue(new DOMException('The operation was aborted.', 'AbortError'));

    renderPage('/documents/doc1/ru/p0001');

    // Wait for the rejection to be processed, then verify no error is shown
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  it('renders index link when no prev page', async () => {
    const pageNoPrev = {
      ...sampleRenderPage,
      nav: { prev: null, next: 'p0002', parent_section: '' },
    } as unknown as RenderPageData;
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(pageNoPrev),
    } as Response);

    renderPage('/documents/walking_skeleton/ru/p0001');

    await waitFor(() => {
      expect(screen.getByText(/Index/)).toBeDefined();
    });
    const link = screen.getByText(/Index/).closest('a');
    expect(link?.getAttribute('href')).toBe('/');
  });
});
