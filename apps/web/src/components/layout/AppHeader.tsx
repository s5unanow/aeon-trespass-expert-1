import { Link, useLocation } from 'react-router';
import { EditionSwitcher } from '../nav/EditionSwitcher';

interface AppHeaderProps {
  documentId: string;
  edition: string;
  pageId?: string;
  documentTitle: string;
  totalPages: number;
  currentPageIndex: number;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function AppHeader({
  documentId,
  edition,
  pageId,
  documentTitle,
  totalPages,
  currentPageIndex,
  sidebarOpen,
  onToggleSidebar,
}: AppHeaderProps) {
  const location = useLocation();
  const isGlossaryPage = location.pathname.endsWith('/glossary');
  const fromPageId = (location.state as { fromPageId?: string } | null)?.fromPageId;

  return (
    <header className="app-header">
      <div className="app-header-left">
        <button
          className="sidebar-toggle"
          onClick={onToggleSidebar}
          aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}
          aria-expanded={sidebarOpen}
        >
          <span className="sidebar-toggle-icon" aria-hidden="true">
            {sidebarOpen ? '\u2715' : '\u2630'}
          </span>
        </button>
        <Link to="/" className="app-header-brand">
          Aeon Trespass
        </Link>
      </div>

      <div className="app-header-center">
        <span className="app-header-title">{documentTitle}</span>
        {pageId && currentPageIndex >= 0 && totalPages > 0 && (
          <span className="app-header-progress">
            Page {currentPageIndex + 1} of {totalPages}
          </span>
        )}
      </div>

      <div className="app-header-right">
        {isGlossaryPage ? (
          <Link
            to={fromPageId ? `/documents/${documentId}/${edition}/${fromPageId}` : '/'}
            className="app-header-link"
          >
            {'\u2190'} Back
          </Link>
        ) : (
          <Link
            to={`/documents/${documentId}/${edition}/glossary`}
            className="app-header-link"
            state={pageId ? { fromPageId: pageId } : undefined}
          >
            Glossary
          </Link>
        )}
        {pageId && (
          <EditionSwitcher documentId={documentId} pageId={pageId} currentEdition={edition} />
        )}
      </div>
    </header>
  );
}
