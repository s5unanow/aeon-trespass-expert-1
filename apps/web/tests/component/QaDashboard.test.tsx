import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QaDashboard } from '../../src/routes/QaDashboard';

const summary = {
  schema_version: 'qa_summary.v1',
  document_id: 'test_doc',
  run_id: 'r',
  counts: { info: 1, warning: 2, error: 1, critical: 0 },
  waived_counts: { info: 0, warning: 0, error: 0, critical: 0 },
  blocking: false,
  record_refs: [],
  review_pack_ref: '',
};

const records = {
  records: [
    {
      schema_version: 'qa_record.v1',
      qa_id: 'qa.1',
      layer: 'structure',
      severity: 'error',
      code: 'PARAGRAPH_TOO_LONG',
      document_id: 'test_doc',
      page_id: 'p0003',
      message: 'Block exceeds limit',
      waived: false,
    },
    {
      schema_version: 'qa_record.v1',
      qa_id: 'qa.2',
      layer: 'terminology',
      severity: 'warning',
      code: 'UNTRANSLATED',
      document_id: 'test_doc',
      page_id: 'p0004',
      message: 'Untranslated segment',
      waived: false,
    },
    {
      schema_version: 'qa_record.v1',
      qa_id: 'qa.3',
      layer: 'terminology',
      severity: 'warning',
      code: 'UNTRANSLATED',
      document_id: 'test_doc',
      page_id: 'p0005',
      message: 'Another untranslated',
      waived: true,
    },
    {
      schema_version: 'qa_record.v1',
      qa_id: 'qa.4',
      layer: 'structure',
      severity: 'info',
      code: 'INFO_ONLY',
      document_id: 'test_doc',
      page_id: null,
      message: 'No page',
      waived: false,
    },
  ],
};

function renderDashboard(initial = '/documents/test_doc/ru/qa') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route path="/documents/:documentId/:edition/qa" element={<QaDashboard />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('QaDashboard', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  function mockQa() {
    fetchSpy.mockImplementation((url: RequestInfo | URL) => {
      const u = String(url);
      if (u.endsWith('qa_summary.json'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) } as Response);
      if (u.endsWith('qa_records.json'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(records) } as Response);
      return Promise.resolve({ ok: false, status: 404 } as Response);
    });
  }

  it('renders findings and severity counts (default hides waived)', async () => {
    mockQa();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    // Default waived=unwaived hides qa.3.
    expect(screen.queryByText('Another untranslated')).toBeNull();
    // 3 unwaived / 4 total.
    expect(screen.getByText(/3 of 4 findings/)).toBeDefined();

    // Severity counts render (one "warning" count pill).
    const countsRegion = screen.getByLabelText('Severity counts');
    expect(countsRegion.textContent).toContain('warning');
    expect(countsRegion.textContent).toContain('error');
  });

  it('filters by severity=error via URL param', async () => {
    mockQa();
    renderDashboard('/documents/test_doc/ru/qa?severity=error');

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    expect(screen.queryByText('Untranslated segment')).toBeNull();
    expect(screen.getByText(/1 of 4 findings/)).toBeDefined();
  });

  it('page_id cell renders a link to the reader page', async () => {
    mockQa();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    const link = screen.getByText('p0003').closest('a');
    expect(link?.getAttribute('href')).toBe('/documents/test_doc/ru/p0003');
  });

  it('can switch the waived filter to show waived records', async () => {
    mockQa();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });

    const waivedSelect = screen.getByLabelText(/Waived/) as HTMLSelectElement;
    fireEvent.change(waivedSelect, { target: { value: 'all' } });

    await waitFor(() => {
      expect(screen.getByText('Another untranslated')).toBeDefined();
    });
  });

  it('filters by page query param and shows a clear button', async () => {
    mockQa();
    renderDashboard('/documents/test_doc/ru/qa?page=p0003');

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    expect(screen.queryByText('Untranslated segment')).toBeNull();
    expect(screen.getByText(/Clear page filter/)).toBeDefined();
  });

  it('renders error state when fetch fails', async () => {
    fetchSpy.mockResolvedValue({ ok: false, status: 500 } as Response);
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });
  });
});
