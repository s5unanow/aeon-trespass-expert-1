import { useCallback, useEffect, useMemo, useState } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router';
import { loadManifest, type DocumentManifest } from '../../lib/api/loadManifest';
import { AppHeader } from './AppHeader';
import { PageSidebar } from './PageSidebar';

function formatDocumentTitle(docId: string): string {
  return docId
    .replace(/_v(\d+)_(\d+)$/, ' v$1.$2')
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((w) => (/^v\d/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ');
}

export function ReaderLayout() {
  const { documentId, edition, pageId } = useParams<{
    documentId: string;
    edition: string;
    pageId: string;
  }>();
  const navigate = useNavigate();
  const [manifest, setManifest] = useState<DocumentManifest | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    if (!documentId || !edition) return;
    let stale = false;
    loadManifest(documentId, edition)
      .then((data) => {
        if (!stale) setManifest(data);
      })
      .catch(() => {
        /* manifest fetch is best-effort for sidebar */
      });
    return () => {
      stale = true;
    };
  }, [documentId, edition]);

  const pages = manifest?.pages ?? [];

  const { currentIndex, prevPageId, nextPageId } = useMemo(() => {
    if (!pageId || pages.length === 0) {
      return { currentIndex: -1, prevPageId: undefined, nextPageId: undefined };
    }
    const idx = pages.findIndex((p) => p.page_id === pageId);
    return {
      currentIndex: idx,
      prevPageId: idx > 0 ? pages[idx - 1].page_id : undefined,
      nextPageId: idx >= 0 && idx < pages.length - 1 ? pages[idx + 1].page_id : undefined,
    };
  }, [pageId, pages]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!documentId || !edition || !pageId) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === 'ArrowLeft' && prevPageId) {
        navigate(`/documents/${documentId}/${edition}/${prevPageId}`);
      } else if (e.key === 'ArrowRight' && nextPageId) {
        navigate(`/documents/${documentId}/${edition}/${nextPageId}`);
      }
    },
    [documentId, edition, pageId, prevPageId, nextPageId, navigate],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const toggleSidebar = useCallback(() => setSidebarOpen((v) => !v), []);
  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  // Route pattern guarantees these params exist; guard just in case.
  if (!documentId || !edition) return <Outlet />;

  const documentTitle = formatDocumentTitle(documentId);

  return (
    <div className="reader-layout">
      <AppHeader
        documentId={documentId}
        edition={edition}
        pageId={pageId}
        documentTitle={documentTitle}
        totalPages={pages.length}
        currentPageIndex={currentIndex}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={toggleSidebar}
      />
      <PageSidebar
        pages={pages}
        documentId={documentId}
        edition={edition}
        currentPageId={pageId}
        pageOffset={manifest?.page_offset}
        isOpen={sidebarOpen}
        onClose={closeSidebar}
      />
      <main className="layout-content">
        <Outlet />
      </main>
    </div>
  );
}
