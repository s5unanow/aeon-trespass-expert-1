import { useEffect, useState } from 'react';
import { useParams } from 'react-router';
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

  return (
    <article className="reader-page">
      <header>
        <SourcePageBadge pageNumber={page.page.source_page_number} />
      </header>
      <section className="reader-content">
        {page.blocks.map((block) => (
          <BlockRenderer key={block.id} block={block} />
        ))}
      </section>
    </article>
  );
}
