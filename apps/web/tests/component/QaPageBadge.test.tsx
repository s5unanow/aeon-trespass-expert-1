import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { QaPageBadge } from '../../src/components/nav/QaPageBadge';
import { clearQaCache } from '../../src/lib/api/loadQa';

function mockBundle(records: { page_id: string; waived?: boolean }[]) {
  return (url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith('qa_summary.json')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response);
    }
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          records: records.map((r, i) => ({
            qa_id: `qa.${i}`,
            layer: 'structure',
            severity: 'warning',
            code: 'C',
            message: 'm',
            ...r,
          })),
        }),
    } as Response);
  };
}

function renderBadge(pageId: string) {
  return render(
    <MemoryRouter>
      <QaPageBadge documentId="test_doc" edition="ru" pageId={pageId} />
    </MemoryRouter>,
  );
}

describe('QaPageBadge', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    clearQaCache();
    cleanup();
  });

  it('shows the count of active findings for the current page', async () => {
    fetchSpy.mockImplementation(
      mockBundle([
        { page_id: 'p0003' },
        { page_id: 'p0003' },
        { page_id: 'p0004' },
      ]),
    );

    renderBadge('p0003');

    await waitFor(() => {
      expect(screen.getByText('2')).toBeDefined();
    });
    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe('/documents/test_doc/ru/qa?page=p0003');
  });

  it('renders nothing when the page has zero active findings', async () => {
    fetchSpy.mockImplementation(
      mockBundle([
        { page_id: 'p0003' },
        // waived findings on this page do not count
        { page_id: 'p0004', waived: true },
      ]),
    );

    renderBadge('p0004');

    // Wait for the bundle to resolve, then assert no badge rendered.
    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.queryByRole('link')).toBeNull();
    });
  });

  it('stays hidden when the QA bundle fails to load', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 404 } as Response);

    renderBadge('p0003');

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalled();
    });
    expect(screen.queryByRole('link')).toBeNull();
  });
});
