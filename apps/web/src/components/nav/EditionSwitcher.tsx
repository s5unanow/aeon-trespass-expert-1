import { Link } from 'react-router';

const EDITIONS = ['en', 'ru'] as const;

interface EditionSwitcherProps {
  documentId: string;
  pageId: string;
  currentEdition: string;
}

/**
 * Toggle between EN and RU editions, preserving the current page.
 * The active edition is shown as a label; the other is a navigation link.
 */
export function EditionSwitcher({ documentId, pageId, currentEdition }: EditionSwitcherProps) {
  return (
    <span className="edition-switcher" role="navigation" aria-label="Edition switcher">
      {EDITIONS.map((ed, i) => (
        <span key={ed}>
          {i > 0 && <span aria-hidden="true"> / </span>}
          {ed === currentEdition ? (
            <strong aria-current="true">{ed.toUpperCase()}</strong>
          ) : (
            <Link to={`/documents/${documentId}/${ed}/${pageId}`}>{ed.toUpperCase()}</Link>
          )}
        </span>
      ))}
    </span>
  );
}
