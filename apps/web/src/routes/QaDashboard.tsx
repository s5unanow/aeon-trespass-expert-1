import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import type { QARecordV1, qaRecordV1 } from '@atr/schemas';
import { loadQa, type QaBundle } from '../lib/api/loadQa';

const SEVERITIES: qaRecordV1.Severity[] = ['info', 'warning', 'error', 'critical'];

type WaivedFilter = 'all' | 'unwaived' | 'waived';

function matchesFilters(
  record: QARecordV1,
  severity: string,
  layer: string,
  code: string,
  page: string,
  waived: WaivedFilter,
): boolean {
  if (severity !== 'all' && record.severity !== severity) return false;
  if (layer !== 'all' && record.layer !== layer) return false;
  if (code !== 'all' && record.code !== code) return false;
  if (page && record.page_id !== page) return false;
  if (waived === 'waived' && !record.waived) return false;
  if (waived === 'unwaived' && record.waived) return false;
  return true;
}

function unique<T extends string>(values: (T | undefined | null)[]): T[] {
  const seen = new Set<T>();
  for (const v of values) {
    if (v) seen.add(v);
  }
  return Array.from(seen).sort();
}

export function QaDashboard() {
  const { documentId, edition } = useParams<{ documentId: string; edition: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [bundle, setBundle] = useState<QaBundle | null>(null);
  const [error, setError] = useState<string | null>(null);

  const severity = searchParams.get('severity') ?? 'all';
  const layer = searchParams.get('layer') ?? 'all';
  const code = searchParams.get('code') ?? 'all';
  const pageFilter = searchParams.get('page') ?? '';
  const waivedRaw = searchParams.get('waived') ?? 'unwaived';
  const waived: WaivedFilter =
    waivedRaw === 'all' || waivedRaw === 'waived' ? waivedRaw : 'unwaived';

  useEffect(() => {
    if (!documentId || !edition) return;
    const controller = new AbortController();
    let stale = false;
    setBundle(null);
    setError(null);
    loadQa(documentId, edition, controller.signal)
      .then((data) => {
        if (!stale) setBundle(data);
      })
      .catch((e: Error) => {
        if (!stale && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition]);

  const { layers, codes } = useMemo(() => {
    const records = bundle?.records ?? [];
    return {
      layers: unique(records.map((r) => r.layer)),
      codes: unique(records.map((r) => r.code)),
    };
  }, [bundle]);

  const filtered = useMemo(() => {
    const records = bundle?.records ?? [];
    return records.filter((r) =>
      matchesFilters(r, severity, layer, code, pageFilter, waived),
    );
  }, [bundle, severity, layer, code, pageFilter, waived]);

  const updateParam = (key: string, value: string, fallback: string): void => {
    const next = new URLSearchParams(searchParams);
    if (value === fallback) {
      next.delete(key);
    } else {
      next.set(key, value);
    }
    setSearchParams(next, { replace: true });
  };

  if (error) return <div role="alert">Error: {error}</div>;
  if (!bundle) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading QA findings">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }

  const counts = bundle.summary.counts ?? { info: 0, warning: 0, error: 0, critical: 0 };
  const totalAll = bundle.records.length;

  return (
    <article className="qa-dashboard fade-in">
      <header className="qa-dashboard-header">
        <h1 className="qa-dashboard-title">QA Findings</h1>
        <div className="qa-dashboard-counts" aria-label="Severity counts">
          {SEVERITIES.map((s) => (
            <span key={s} className={`qa-count qa-count-${s}`}>
              <strong>{counts[s] ?? 0}</strong> {s}
            </span>
          ))}
        </div>
        <div className="qa-dashboard-filters">
          <label>
            Severity:
            <select
              value={severity}
              onChange={(e) => updateParam('severity', e.target.value, 'all')}
            >
              <option value="all">All</option>
              {SEVERITIES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Layer:
            <select value={layer} onChange={(e) => updateParam('layer', e.target.value, 'all')}>
              <option value="all">All</option>
              {layers.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label>
            Code:
            <select value={code} onChange={(e) => updateParam('code', e.target.value, 'all')}>
              <option value="all">All</option>
              {codes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label>
            Waived:
            <select
              value={waived}
              onChange={(e) => updateParam('waived', e.target.value, 'unwaived')}
            >
              <option value="unwaived">Unwaived only</option>
              <option value="all">All</option>
              <option value="waived">Waived only</option>
            </select>
          </label>
          {pageFilter && (
            <button
              type="button"
              className="qa-clear-page"
              onClick={() => updateParam('page', '', '')}
            >
              Clear page filter ({pageFilter})
            </button>
          )}
        </div>
        <p className="qa-dashboard-count">
          {filtered.length} of {totalAll} findings
        </p>
      </header>

      {filtered.length === 0 ? (
        <p className="qa-empty">No findings match the current filters.</p>
      ) : (
        <table className="qa-table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Layer</th>
              <th>Code</th>
              <th>Page</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.qa_id} className={`qa-row qa-row-${r.severity}`}>
                <td>{r.severity}</td>
                <td>{r.layer}</td>
                <td>{r.code}</td>
                <td>
                  {r.page_id ? (
                    <Link
                      to={`/documents/${documentId}/${edition}/${r.page_id}`}
                      className="qa-page-link"
                    >
                      {r.page_id}
                    </Link>
                  ) : (
                    <span className="qa-page-none">—</span>
                  )}
                </td>
                <td>{r.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  );
}

export default QaDashboard;
