import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QaDashboard } from '../../src/routes/QaDashboard';
import { clearQaCache } from '../../src/lib/api/loadQa';

// Mocks match the public DTO shapes written by scripts/_export_qa.py
// (PublicQASummaryV1 / PublicQARecordSetV1). Internal fields such as
// run_id, record_refs, review_pack_ref, per-record schema_version, and
// per-record document_id are intentionally absent — if the reader code ever
// starts depending on them, that is itself a regression of S5U-689.
const summary = {
  schema_version: 'public_qa_summary.v1',
  document_id: 'test_doc',
  edition: 'ru',
  counts: { info: 1, warning: 2, error: 1, critical: 0 },
  waived_counts: { info: 0, warning: 0, error: 0, critical: 0 },
  blocking: false,
};

const records = {
  schema_version: 'public_qa_record_set.v1',
  records: [
    {
      qa_id: 'qa.1',
      layer: 'structure',
      severity: 'error',
      code: 'PARAGRAPH_TOO_LONG',
      page_id: 'p0003',
      entity_ref: 'p0003.b008',
      message: 'Block exceeds limit',
      waived: false,
    },
    {
      qa_id: 'qa.2',
      layer: 'terminology',
      severity: 'warning',
      code: 'UNTRANSLATED',
      page_id: 'p0004',
      message: 'Untranslated segment',
      waived: false,
    },
    {
      qa_id: 'qa.3',
      layer: 'terminology',
      severity: 'warning',
      code: 'UNTRANSLATED',
      page_id: 'p0005',
      message: 'Another untranslated',
      waived: true,
    },
    {
      qa_id: 'qa.4',
      layer: 'structure',
      severity: 'info',
      code: 'INFO_ONLY',
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
    clearQaCache();
    cleanup();
  });

  // QAMetricsV1 payload as written verbatim by scripts/_export_qa.py.
  const metrics = {
    schema_version: 'qa_metrics.v1',
    document_id: 'test_doc',
    edition: 'ru',
    pages_total: 10,
    pages_with_findings: 4,
    clean_page_rate: 0.6,
    findings_by_severity: { info: 1, warning: 2, error: 1, critical: 0 },
    findings_by_layer: { terminology: 2, structure: 2 },
    findings_by_code_top10: [{ code: 'UNTRANSLATED', count: 2 }],
    waived_count: 1,
    blocking_count: 0,
    avg_findings_per_page: 0.4,
  };

  // Default mock: summary + records present, qa_metrics.json absent (404).
  // This mirrors the RU edition today, which ships no metrics artifact.
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

  // Metrics-present variant: qa_metrics.json resolves alongside the table data.
  function mockQaWithMetrics() {
    fetchSpy.mockImplementation((url: RequestInfo | URL) => {
      const u = String(url);
      if (u.endsWith('qa_summary.json'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) } as Response);
      if (u.endsWith('qa_records.json'))
        return Promise.resolve({ ok: true, json: () => Promise.resolve(records) } as Response);
      if (u.endsWith('qa_metrics.json'))
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(metrics),
        } as Response);
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

  it('page_id cell renders a link to the reader page with entity_ref hash', async () => {
    mockQa();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    const link = screen.getByText('p0003').closest('a');
    expect(link?.getAttribute('href')).toBe('/documents/test_doc/ru/p0003#p0003.b008');
  });

  it('omits the hash when a finding has no entity_ref', async () => {
    mockQa();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Untranslated segment')).toBeDefined();
    });
    const link = screen.getByText('p0004').closest('a');
    expect(link?.getAttribute('href')).toBe('/documents/test_doc/ru/p0004');
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

  it('renders the QA health cards when qa_metrics.json is present', async () => {
    mockQaWithMetrics();
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    await waitFor(() => {
      expect(screen.getByLabelText('QA health summary')).toBeDefined();
    });
    // clean_page_rate 0.6 → 60%; blocking_count 0; top code from metrics.
    expect(screen.getByText('60%')).toBeDefined();
    expect(screen.getByText('Top codes')).toBeDefined();
  });

  it('degrades gracefully (no health cards, table intact) when qa_metrics.json is absent', async () => {
    mockQa(); // qa_metrics.json → 404
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Block exceeds limit')).toBeDefined();
    });
    // Findings table still renders fully (must-not-break).
    expect(screen.getByText(/3 of 4 findings/)).toBeDefined();
    // Health summary is absent — the dashboard does not throw or block.
    expect(screen.queryByLabelText('QA health summary')).toBeNull();
  });
});
