import { useEffect, useRef } from 'react';
import { Link } from 'react-router';

interface SidebarPage {
  page_id: string;
  title?: string;
  depth?: number;
}

interface PageSidebarProps {
  pages: SidebarPage[];
  documentId: string;
  edition: string;
  currentPageId?: string;
  isOpen: boolean;
  onClose: () => void;
}

function formatPageNumber(pageId: string): string {
  const num = parseInt(pageId.replace(/^p/, ''), 10);
  return Number.isNaN(num) ? pageId : String(num);
}

export function PageSidebar({
  pages,
  documentId,
  edition,
  currentPageId,
  isOpen,
  onClose,
}: PageSidebarProps) {
  const activeRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView?.({ block: 'nearest' });
    }
  }, [currentPageId]);

  return (
    <>
      <nav className={`sidebar ${isOpen ? 'sidebar--open' : ''}`} aria-label="Page navigation">
        <ul className="sidebar-list">
          {pages.map((page) => {
            const isCurrent = page.page_id === currentPageId;
            const isSection = page.depth === 0;
            const linkClass = [
              'sidebar-link',
              isCurrent && 'sidebar-link--active',
              isSection && 'sidebar-link--section',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <li key={page.page_id}>
                <Link
                  ref={isCurrent ? activeRef : undefined}
                  to={`/documents/${documentId}/${edition}/${page.page_id}`}
                  className={linkClass}
                  aria-current={isCurrent ? 'page' : undefined}
                  onClick={onClose}
                >
                  <span className="sidebar-link-number">{formatPageNumber(page.page_id)}</span>
                  {page.title && <span className="sidebar-link-title">{page.title}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {isOpen && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
    </>
  );
}
