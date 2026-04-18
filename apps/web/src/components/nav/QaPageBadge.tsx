import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { loadQa } from '../../lib/api/loadQa';

interface QaPageBadgeProps {
  documentId: string;
  edition: string;
  pageId: string;
}

/**
 * Small indicator showing the number of active (unwaived) QA findings for the
 * current reader page. Links to the dashboard pre-filtered to that page.
 *
 * Renders nothing until the bundle is loaded, and nothing when the count is 0
 * so reader pages without findings stay visually uncluttered.
 */
export function QaPageBadge({ documentId, edition, pageId }: QaPageBadgeProps) {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let stale = false;
    loadQa(documentId, edition, controller.signal)
      .then((bundle) => {
        if (stale) return;
        const n = bundle.records.filter((r) => r.page_id === pageId && !r.waived).length;
        setCount(n);
      })
      .catch(() => {
        /* QA bundle is optional; badge simply stays hidden when unavailable. */
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  if (count === null || count === 0) return null;

  return (
    <Link
      to={`/documents/${documentId}/${edition}/qa?page=${pageId}`}
      className="qa-page-badge"
      aria-label={`${count} QA finding${count === 1 ? '' : 's'} on this page`}
    >
      <span className="qa-page-badge-count">{count}</span>
      <span className="qa-page-badge-label">QA</span>
    </Link>
  );
}
