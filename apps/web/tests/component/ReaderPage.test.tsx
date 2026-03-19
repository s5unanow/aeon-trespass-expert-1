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
        <Route path="/documents/:documentId/:pageId" element={<ReaderPage />} />
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

    renderPage('/documents/walking_skeleton/p0001');

    await waitFor(() => {
      expect(screen.getByText('Проверка атаки')).toBeDefined();
    });
    expect(screen.getByText('Получите 1')).toBeDefined();
    expect(screen.getByRole('img', { name: 'Прогресс' })).toBeDefined();
    expect(screen.getByText('p.1')).toBeDefined();
  });

  it('shows loading state before data arrives', () => {
    fetchSpy.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage('/documents/walking_skeleton/p0001');
    expect(screen.getByText('Loading...')).toBeDefined();
  });

  it('shows error when fetch fails', async () => {
    fetchSpy.mockRejectedValue(new Error('network down'));
    renderPage('/documents/walking_skeleton/p0001');

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

    renderPage('/documents/walking_skeleton/p0002');

    await waitFor(() => {
      expect(screen.getByText(/Prev/)).toBeDefined();
    });
    const prev = screen.getByText(/Prev/).closest('a');
    const next = screen.getByText(/Next/).closest('a');
    expect(prev?.getAttribute('href')).toBe('/documents/walking_skeleton/p0001');
    expect(next?.getAttribute('href')).toBe('/documents/walking_skeleton/p0003');
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

    renderPage('/documents/walking_skeleton/p0001');

    await waitFor(() => {
      expect(screen.getByText(/Index/)).toBeDefined();
    });
    const link = screen.getByText(/Index/).closest('a');
    expect(link?.getAttribute('href')).toBe('/');
  });
});
