import { useEffect, useState } from 'react';
import { useLocation, useOutletContext, useParams } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { FacsimilePage } from '../components/reader/FacsimilePage';
import { FeedbackButton } from '../components/reader/FeedbackButton';
import { SourcePageBadge } from '../components/nav/SourcePageBadge';
import { PageGlossaryProvider } from '../contexts/PageContext';

/** Lifetime of the deep-link anchor highlight before it fades out (ms). */
const ANCHOR_HIGHLIGHT_MS = 1600;

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

  // Scroll to the hash target and highlight it once the page content has
  // rendered. React Router navigates via pushState, which (a) mounts the
  // element after the browser's native anchor scroll fired — so we re-scroll —
  // and (b) does NOT update the active `:target` fragment in an SPA navigation.
  // We deliberately drive the highlight with a transient `anchor-highlight`
  // class rather than re-bouncing `window.location.hash`: that bounce pushed
  // two spurious history entries (`…#` then `…#hash`), so Back landed back on
  // the page instead of leaving it. Same fix the glossary deep link uses
  // (`glossary-card-highlight`, S5U-584). `QaDashboard` links into reader
  // anchors (`pageId#entity_ref`), so this is a live navigation path.
  useEffect(() => {
    if (!page) return;
    const hash = location.hash.slice(1);
    if (!hash) return;
    const el = document.getElementById(hash);
    if (!el) return;
    el.scrollIntoView({ block: 'start' });
    el.classList.add('anchor-highlight');
    const timer = window.setTimeout(() => {
      el.classList.remove('anchor-highlight');
    }, ANCHOR_HIGHLIGHT_MS);
    return () => {
      window.clearTimeout(timer);
      el.classList.remove('anchor-highlight');
    };
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
    // GlossaryProvider was lifted to ReaderLayout (S5U-1225) so the shared
    // glossary context is not torn down by the `page=null` reset on every page
    // turn. Only the per-page mention provider lives here.
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
  );
}
