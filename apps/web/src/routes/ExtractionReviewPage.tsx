import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { ReviewWorkspace } from '../components/review/ReviewWorkspace';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { reviewStorageKey } from '../lib/review/persistence';
import '../styles/review.css';

export function ExtractionReviewPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
  const [page, setPage] = useState<RenderPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId || !edition || !pageId) return;
    const controller = new AbortController();
    let stale = false;
    setPage(null);
    setError(null);
    loadRenderPage(documentId, pageId, edition, controller.signal)
      .then((loaded) => {
        if (!stale) setPage(loaded);
      })
      .catch((caught: unknown) => {
        if (!stale && (!(caught instanceof Error) || caught.name !== 'AbortError')) {
          setError(caught instanceof Error ? caught.message : 'Unable to load review page');
        }
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  if (error) return <div role="alert">Error: {error}</div>;
  if (!page || !documentId || !edition || !pageId) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading extraction review">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }
  const storageKey = reviewStorageKey(documentId, edition, pageId);
  return (
    <ReviewWorkspace
      key={storageKey}
      page={page}
      documentId={documentId}
      edition={edition}
      pageId={pageId}
      storageKey={storageKey}
    />
  );
}
