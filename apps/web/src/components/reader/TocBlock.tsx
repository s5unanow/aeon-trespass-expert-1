import { Link, useParams } from 'react-router';
import type { TocEntry } from '../../lib/render/toc';

export interface TocBlockProps {
  id: string;
  entries: TocEntry[];
  pageOffset?: number;
}

function pageIdFromPrinted(pageNumber: string, offset: number): string {
  const n = parseInt(pageNumber, 10);
  if (Number.isNaN(n)) return '';
  return `p${String(n + offset).padStart(4, '0')}`;
}

export function TocBlock({ id, entries, pageOffset = 0 }: TocBlockProps) {
  const { documentId, edition } = useParams<{ documentId: string; edition: string }>();

  return (
    <nav id={id} className="reader-toc" aria-label="Table of contents">
      <ul className="reader-toc-list">
        {entries.map((entry, i) => {
          const pid = pageIdFromPrinted(entry.pageNumber, pageOffset);
          const href =
            documentId && edition && pid ? `/documents/${documentId}/${edition}/${pid}` : undefined;

          return (
            <li key={i} className="reader-toc-entry">
              {href ? (
                <Link to={href} className="reader-toc-link">
                  <span className="reader-toc-title">{entry.title}</span>
                  <span className="reader-toc-dots" aria-hidden="true" />
                  <span className="reader-toc-page">{entry.pageNumber}</span>
                </Link>
              ) : (
                <>
                  <span className="reader-toc-title">{entry.title}</span>
                  <span className="reader-toc-dots" aria-hidden="true" />
                  <span className="reader-toc-page">{entry.pageNumber}</span>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
