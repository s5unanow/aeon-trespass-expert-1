import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router';
import { useEffect } from 'react';
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

  beforeEach(() => {
    // Reset the documentElement.lang between tests so each assertion reflects
    // the layout's own behavior, not leftover state from a prior test.
    document.documentElement.removeAttribute('lang');
  });

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
    document.documentElement.removeAttribute('lang');
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

  it('shows back link instead of glossary link on glossary page', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/glossary');

    await waitFor(() => {
      expect(screen.getByText(/Back/)).toBeDefined();
    });
    const glossaryLink = screen.queryByRole('link', { name: 'Glossary' });
    expect(glossaryLink).toBeNull();
  });

  it('back link on glossary points to referring page when state provided', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/documents/ato_core_v1_1/ru/glossary',
            state: { fromPageId: 'p0002' },
          },
        ]}
      >
        <Routes>
          <Route path="/documents/:documentId/:edition" element={<ReaderLayout />}>
            <Route path=":pageId" element={<div>Page</div>} />
            <Route path="glossary" element={<div>Glossary</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      const back = screen.getByText(/Back/).closest('a');
      expect(back?.getAttribute('href')).toBe('/documents/ato_core_v1_1/ru/p0002');
    });
  });

  it('back link on glossary falls back to home when no state', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/glossary');

    await waitFor(() => {
      const back = screen.getByText(/Back/).closest('a');
      expect(back?.getAttribute('href')).toBe('/');
    });
  });

  // --- S5U-702: HTML lang metadata tracks the active edition ---

  it('sets document.documentElement.lang to "ru" on a RU reader route', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/ru/p0002');

    await waitFor(() => {
      expect(document.documentElement.lang).toBe('ru');
    });
  });

  it('sets document.documentElement.lang to "en" on an EN reader route', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    renderLayout('/documents/ato_core_v1_1/en/p0001');

    await waitFor(() => {
      expect(document.documentElement.lang).toBe('en');
    });
  });

  it('updates lang on edition transition without leaving stale metadata', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(MANIFEST),
    } as Response);

    function TransitionHarness({ target }: { target: string }) {
      const navigate = useNavigate();
      useEffect(() => {
        navigate(target);
      }, [navigate, target]);
      return null;
    }

    render(
      <MemoryRouter initialEntries={['/documents/ato_core_v1_1/en/p0001']}>
        <Routes>
          <Route path="/documents/:documentId/:edition" element={<ReaderLayout />}>
            <Route
              path=":pageId"
              element={
                <>
                  <div data-testid="page-outlet">Page content</div>
                  <TransitionHarness target="/documents/ato_core_v1_1/ru/p0002" />
                </>
              }
            />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(document.documentElement.lang).toBe('ru');
    });
  });
});
