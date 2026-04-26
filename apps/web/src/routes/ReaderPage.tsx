import { useEffect, useState } from 'react';
import { useLocation, useOutletContext, useParams } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { FacsimilePage } from '../components/reader/FacsimilePage';
import { FeedbackButton } from '../components/reader/FeedbackButton';
import { SourcePageBadge } from '../components/nav/SourcePageBadge';
import { GlossaryProvider } from '../contexts/GlossaryContext';
import { PageGlossaryProvider } from '../contexts/PageContext';

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
  const location = useLocation();

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

  // Scroll to the hash target and activate the :target highlight once the page
  // content has rendered. Two quirks handled here:
  //   1. React Router pushes history via pushState, so the element often mounts
  //      after the browser's native anchor scroll fired — we re-scroll.
  //   2. pushState does NOT update the active fragment, so :target never
  //      matches in an SPA navigation. If it doesn't, reassign location.hash
  //      to force the browser to re-evaluate :target (after we've already
  //      scrolled, so the user won't see a jump).
  useEffect(() => {
    if (!page) return;
    const hash = location.hash.slice(1);
    if (!hash) return;
    const el = document.getElementById(hash);
    if (!el) return;
    el.scrollIntoView({ block: 'start' });
    if (!el.matches(':target')) {
      window.location.hash = '';
      window.location.hash = hash;
    }
  }, [page, location.hash]);

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
      <PageGlossaryProvider mentions={page.glossary_mentions}>
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
          <FeedbackButton documentId={documentId!} edition={edition!} pageId={pageId!} />
        </article>
      </PageGlossaryProvider>
    </GlossaryProvider>
  );
}
