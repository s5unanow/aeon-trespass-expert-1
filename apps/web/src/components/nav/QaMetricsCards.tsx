import type { QAMetricsV1 } from '@atr/schemas';

interface QaMetricsCardsProps {
  metrics: QAMetricsV1;
}

const SEVERITY_ORDER: (keyof NonNullable<QAMetricsV1['findings_by_severity']>)[] = [
  'info',
  'warning',
  'error',
  'critical',
];

function formatPercent(rate: number): string {
  // clean_page_rate is a 0..1 fraction in the artifact.
  return `${Math.round(rate * 1000) / 10}%`;
}

function topEntries(record: Record<string, number>, limit: number): [string, number][] {
  return Object.entries(record)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}

/**
 * QA health summary cards (S5U-874) driven by the exported ``qa_metrics.json``
 * (`QAMetricsV1`). Renders the high-value health signals — clean-page rate,
 * blocking count, severity distribution, and the top layers / codes — above
 * the existing filtered findings table.
 *
 * Presentational only: the parent route owns loading and degrade-when-absent.
 * Scope is deliberately QA-only; no ops / CI / agent data is rendered here.
 */
export function QaMetricsCards({ metrics }: QaMetricsCardsProps) {
  const severity = metrics.findings_by_severity ?? {};
  const layers = topEntries(metrics.findings_by_layer ?? {}, 5);
  const codes = (metrics.findings_by_code_top10 ?? []).slice(0, 5);

  return (
    <section className="qa-metrics" aria-label="QA health summary">
      <h2 className="qa-metrics-title">QA Health</h2>
      <div className="qa-metrics-cards">
        <div className="qa-metric-card">
          <span className="qa-metric-value">{formatPercent(metrics.clean_page_rate ?? 0)}</span>
          <span className="qa-metric-label">Clean-page rate</span>
          <span className="qa-metric-sub">
            {metrics.pages_with_findings ?? 0} of {metrics.pages_total ?? 0} pages with findings
          </span>
        </div>
        <div
          className={`qa-metric-card${(metrics.blocking_count ?? 0) > 0 ? ' qa-metric-card-alert' : ''}`}
        >
          <span className="qa-metric-value">{metrics.blocking_count ?? 0}</span>
          <span className="qa-metric-label">Blocking findings</span>
          <span className="qa-metric-sub">
            {(metrics.avg_findings_per_page ?? 0).toFixed(1)} avg per page
          </span>
        </div>
        <div className="qa-metric-card">
          <span className="qa-metric-label">Severity distribution</span>
          <ul className="qa-metric-dist">
            {SEVERITY_ORDER.map((s) => (
              <li key={s} className={`qa-metric-dist-row qa-count-${s}`}>
                <span className="qa-metric-dist-label">{s}</span>
                <strong className="qa-metric-dist-count">{severity[s] ?? 0}</strong>
              </li>
            ))}
          </ul>
        </div>
        <div className="qa-metric-card">
          <span className="qa-metric-label">Top layers</span>
          <ul className="qa-metric-dist">
            {layers.length === 0 ? (
              <li className="qa-metric-dist-empty">—</li>
            ) : (
              layers.map(([layer, count]) => (
                <li key={layer} className="qa-metric-dist-row">
                  <span className="qa-metric-dist-label">{layer}</span>
                  <strong className="qa-metric-dist-count">{count}</strong>
                </li>
              ))
            )}
          </ul>
        </div>
        <div className="qa-metric-card">
          <span className="qa-metric-label">Top codes</span>
          <ul className="qa-metric-dist">
            {codes.length === 0 ? (
              <li className="qa-metric-dist-empty">—</li>
            ) : (
              codes.map((c) => (
                <li key={c.code} className="qa-metric-dist-row">
                  <span className="qa-metric-dist-label qa-metric-code">{c.code}</span>
                  <strong className="qa-metric-dist-count">{c.count ?? 0}</strong>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </section>
  );
}
