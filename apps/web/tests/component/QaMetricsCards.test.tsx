import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import type { QAMetricsV1 } from '@atr/schemas';
import { QaMetricsCards } from '../../src/components/nav/QaMetricsCards';

const METRICS: QAMetricsV1 = {
  schema_version: 'qa_metrics.v1',
  document_id: 'ato_core_v1_1',
  edition: 'en',
  pages_total: 83,
  pages_with_findings: 50,
  clean_page_rate: 0.397,
  findings_by_severity: { info: 70, warning: 426, error: 1250, critical: 3 },
  findings_by_layer: { terminology: 1249, render: 370, structure: 27 },
  findings_by_code_top10: [
    { code: 'UNTRANSLATED_TEXT', count: 1249 },
    { code: 'DECORATIVE_ICON_LEAKED', count: 192 },
  ],
  waived_count: 0,
  blocking_count: 1250,
  avg_findings_per_page: 21.04,
};

describe('QaMetricsCards', () => {
  afterEach(() => cleanup());

  it('renders the clean-page rate as a percentage of the 0..1 fraction', () => {
    const { getByText } = render(<QaMetricsCards metrics={METRICS} />);
    expect(getByText('39.7%')).toBeTruthy();
  });

  it('renders the blocking count and avg-per-page sub-stat', () => {
    const { container } = render(<QaMetricsCards metrics={METRICS} />);
    const text = container.textContent ?? '';
    expect(text).toContain('1250');
    expect(text).toContain('21.0 avg per page');
  });

  it('renders the full severity distribution including non-zero criticals', () => {
    const { container } = render(<QaMetricsCards metrics={METRICS} />);
    const text = container.textContent ?? '';
    for (const sev of ['info', 'warning', 'error', 'critical']) {
      expect(text).toContain(sev);
    }
    const criticalRow = container.querySelector('.qa-count-critical .qa-metric-dist-count');
    expect(criticalRow?.textContent).toBe('3');
  });

  it('renders top layers and top codes', () => {
    const { container } = render(<QaMetricsCards metrics={METRICS} />);
    const text = container.textContent ?? '';
    expect(text).toContain('terminology');
    expect(text).toContain('UNTRANSLATED_TEXT');
    expect(text).toContain('DECORATIVE_ICON_LEAKED');
  });

  it('flags a non-zero blocking count with the alert modifier class', () => {
    const { container } = render(<QaMetricsCards metrics={METRICS} />);
    expect(container.querySelector('.qa-metric-card-alert')).not.toBeNull();
  });

  it('tolerates a sparse metrics payload (missing distribution fields)', () => {
    const sparse: QAMetricsV1 = { document_id: 'x' };
    const { container } = render(<QaMetricsCards metrics={sparse} />);
    const text = container.textContent ?? '';
    expect(text).toContain('0%');
    expect(container.querySelector('.qa-metric-card-alert')).toBeNull();
    expect(container.querySelectorAll('.qa-metric-dist-empty').length).toBeGreaterThan(0);
  });
});
