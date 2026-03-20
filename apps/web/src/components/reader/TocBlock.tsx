import type { TocEntry } from '../../lib/render/toc';

interface TocBlockProps {
  id: string;
  entries: TocEntry[];
}

export function TocBlock({ id, entries }: TocBlockProps) {
  return (
    <nav id={id} className="reader-toc" aria-label="Table of contents">
      <ul className="reader-toc-list">
        {entries.map((entry, i) => (
          <li key={i} className="reader-toc-entry">
            <span className="reader-toc-title">{entry.title}</span>
            <span className="reader-toc-dots" aria-hidden="true" />
            <span className="reader-toc-page">{entry.pageNumber}</span>
          </li>
        ))}
      </ul>
    </nav>
  );
}
