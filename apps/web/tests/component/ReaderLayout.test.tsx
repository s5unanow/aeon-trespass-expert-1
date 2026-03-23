import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { ReaderLayout } from '../../src/components/layout/ReaderLayout';

const MANIFEST = {
  document_id: 'ato_core_v1_1',
  pages: [
    { page_id: 'p0001', title: 'Intro' },
    { page_id: 'p0002', title: 'Setup' },
    { page_id: 'p0003', title: 'Rules' },
  ],
};

function renderLayout(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/documents/:documentId/:edition" element={<ReaderLayout />}>
          <Route path=":pageId" element={<div data-testid="page-outlet">Page content</div>} />
          <Route path="glossary" element={<div data-testid="glossary-outlet">Glossary</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ReaderLayout', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('renders header with document title and brand link', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(screen.getByText('Aeon Trespass')).toBeDefined();
    });
    const brand = screen.getByText('Aeon Trespass').closest('a');
    expect(brand?.getAttribute('href')).toBe('/');
  });

  it('renders sidebar with page list from manifest', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(screen.getByText('Intro')).toBeDefined();
    });
    expect(screen.getByText('Setup')).toBeDefined();
    expect(screen.getByText('Rules')).toBeDefined();
  });

  it('highlights the current page in sidebar', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      const activeLink = screen.getByRole('link', { current: 'page' });
      expect(activeLink).toBeDefined();
      expect(activeLink.textContent).toContain('Setup');
    });
  });

  it('shows page progress indicator', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(screen.getByText('Page 2 of 3')).toBeDefined();
    });
  });

  it('renders child outlet', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(screen.getByTestId('page-outlet')).toBeDefined();
    });
  });

  it('navigates with arrow keys', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(screen.getByText('Page 2 of 3')).toBeDefined();
    });

    fireEvent.keyDown(window, { key: 'ArrowLeft' });

    await waitFor(() => {
      expect(screen.getByText('Page 1 of 3')).toBeDefined();
    });
  });

  it('renders glossary link in header', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      const link = screen.getByText('Glossary').closest('a');
      expect(link?.getAttribute('href')).toBe('/documents/ato_core_v1_1/ru/glossary');
    });
  });
});
