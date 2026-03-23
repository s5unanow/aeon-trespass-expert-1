import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { loadRenderPage } from '../lib/api/loadRenderPage';
import type { RenderPageData } from '../lib/render/types';
import { BlockRenderer } from '../components/reader/BlockRenderer';
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

  return (
    <GlossaryProvider documentId={documentId!} edition={edition!}>
      <article className="reader-page">
        <header>
          <SourcePageBadge pageNumber={page.page.source_page_number} />
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
