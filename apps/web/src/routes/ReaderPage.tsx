import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { EditionSwitcher } from '../components/nav/EditionSwitcher';
import { SourcePageBadge } from '../components/nav/SourcePageBadge';
import { GlossaryProvider } from '../contexts/GlossaryContext';

export function ReaderPage() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
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
    return <div>Loading...</div>;
  }

  const prev = page.nav?.prev;
  const next = page.nav?.next;

  return (
    <GlossaryProvider documentId={documentId!} edition={edition!}>
      <article className="reader-page">
        <header>
          <nav className="reader-nav">
            <span>
              {prev ? (
                <Link to={`/documents/${documentId}/${edition}/${prev}`}>&larr; Prev</Link>
              ) : (
                <Link to="/">&larr; Index</Link>
              )}
            </span>
            <span className="reader-nav-right">
              <Link
                to={`/documents/${documentId}/${edition}/glossary`}
                className="glossary-nav-link"
              >
                Glossary
              </Link>
              <EditionSwitcher
                documentId={documentId!}
                pageId={pageId!}
                currentEdition={edition!}
              />
              <SourcePageBadge pageNumber={page.page.source_page_number} />
            </span>
            <span>
              {next ? (
                <Link to={`/documents/${documentId}/${edition}/${next}`}>Next &rarr;</Link>
              ) : (
                <span />
              )}
            </span>
          </nav>
        </header>
        <section className="reader-content">
          {page.blocks.map((block) => (
            <BlockRenderer key={block.id} block={block} figures={page.figures} />
          ))}
        </section>
      </article>
    </GlossaryProvider>
  );
}
