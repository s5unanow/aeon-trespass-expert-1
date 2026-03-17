import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
import { SourcePageBadge } from '../components/nav/SourcePageBadge';

export function ReaderPage() {
  const { documentId, pageId } = useParams<{ documentId: string; pageId: string }>();
  const [page, setPage] = useState<RenderPageData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!documentId || !pageId) return;
    setPage(null);
    setError(null);
    loadRenderPage(documentId, pageId)
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [documentId, pageId]);

  if (error) {
    return <div role="alert">Error: {error}</div>;
  }
  if (!page) {
    return <div>Loading...</div>;
  }

  const prev = page.nav?.prev;
  const next = page.nav?.next;

  return (
    <article className="reader-page">
      <header>
        <nav style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <span>
            {prev ? (
              <Link to={`/documents/${documentId}/${prev}`}>&larr; Prev</Link>
            ) : (
              <Link to="/">&larr; Index</Link>
            )}
          </span>
          <SourcePageBadge pageNumber={page.page.source_page_number} />
          <span>
            {next ? (
              <Link to={`/documents/${documentId}/${next}`}>Next &rarr;</Link>
            ) : (
              <span />
            )}
          </span>
        </nav>
      </header>
      <section className="reader-content">
        {page.blocks.map((block) => (
          <BlockRenderer key={block.id} block={block} />
        ))}
      </section>
    </article>
  );
}
