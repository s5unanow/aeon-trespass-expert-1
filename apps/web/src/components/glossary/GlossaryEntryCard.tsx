import { Link, useParams } from 'react-router';
import type { glossaryPayloadV1 } from '@atr/schemas';
import { IconInline } from '../reader/IconInline';

interface GlossaryEntryCardProps {
  entry: glossaryPayloadV1.GlossaryEntryV1;
}

export function GlossaryEntryCard({ entry }: GlossaryEntryCardProps) {
  const { documentId, edition } = useParams<{ documentId: string; edition: string }>();
  const aliases = entry.aliases ?? [];
  const pageRefs = entry.page_refs ?? [];

  return (
    <div className="glossary-card">
      <div className="glossary-card-header">
        {entry.icon_binding && (
          <span className="glossary-card-icon">
            <IconInline symbolId={entry.icon_binding} />
          </span>
        )}
        <div>
          <h3 className="glossary-card-term">{entry.preferred_term}</h3>
          {entry.source_term && <span className="glossary-card-source">{entry.source_term}</span>}
        </div>
      </div>
      {aliases.length > 0 && (
        <div className="glossary-card-aliases">
          {aliases.map((alias) => (
            <span key={alias} className="glossary-alias-pill">
              {alias}
            </span>
          ))}
        </div>
      )}
      {entry.notes && <p className="glossary-card-notes">{entry.notes}</p>}
      {pageRefs.length > 0 && (
        <div className="glossary-card-pages">
          <span className="glossary-card-pages-label">Pages:</span>
          {pageRefs.map((ref) => (
            <Link
              key={ref.page_id}
              to={`/documents/${documentId}/${edition}/${ref.page_id}`}
              className="glossary-page-link"
            >
              {ref.source_page_number}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
