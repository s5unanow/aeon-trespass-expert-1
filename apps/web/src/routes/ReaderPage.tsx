import { useEffect, useState } from 'react';
import { useOutletContext, useParams } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { FacsimilePage } from '../components/reader/FacsimilePage';
import { SourcePageBadge } from '../components/nav/SourcePageBadge';
import { GlossaryProvider } from '../contexts/GlossaryContext';

export function ReaderPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
  const outletContext = useOutletContext<{ pageOffset?: number } | null>();
  const pageOffset = outletContext?.pageOffset ?? 0;
  const [page, setPage] = useState<RenderPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId || !pageId || !edition) return;
    const controller = new AbortController();
    let stale = false;
    setPage(null);
    setError(null);
    loadRenderPage(documentId, pageId, edition, controller.signal)
      .then((data) => {
        if (!stale) setPage(data);
      })
      .catch((e) => {
        if (!stale && e.name !== 'AbortError') setError(e.message);
      });
    return () => {
      stale = true;
      controller.abort();
    };
  }, [documentId, edition, pageId]);

  if (error) {
    return <div role="alert">Error: {error}</div>;
  }
  if (!page) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading page">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-line" />
        <div className="skeleton-bone skeleton-line" />
        <div className="skeleton-bone skeleton-line" />
        <div className="skeleton-bone skeleton-block" />
        <div className="skeleton-bone skeleton-line" />
        <div className="skeleton-bone skeleton-line" />
      </div>
    );
  }

  return (
    <GlossaryProvider documentId={documentId!} edition={edition!}>
      <article className="reader-page fade-in">
        <header>
          <SourcePageBadge pageNumber={page.page.source_page_number} />
        </header>
        <section className="reader-content">
          {page.presentation_mode === 'facsimile' && page.facsimile ? (
            <FacsimilePage
              facsimile={page.facsimile}
              pageTitle={page.page.title}
              pageNumber={page.page.source_page_number}
            />
          ) : (
            page.blocks.map((block) => (
              <BlockRenderer
                key={block.id}
                block={block}
                figures={page.figures}
                pageOffset={pageOffset}
              />
            ))
          )}
        </section>
      </article>
    </GlossaryProvider>
  );
}
