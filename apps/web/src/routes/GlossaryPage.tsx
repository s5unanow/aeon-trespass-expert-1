import { useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router';
import type { GlossaryPayloadV1, glossaryPayloadV1 } from '@atr/schemas';
import { loadGlossary } from '../lib/api/loadGlossary';
import { GlossaryEntryCard } from '../components/glossary/GlossaryEntryCard';

function matchesQuery(entry: glossaryPayloadV1.GlossaryEntryV1, query: string): boolean {
  const q = query.toLowerCase();
  if (entry.preferred_term.toLowerCase().includes(q)) return true;
  if (entry.source_term?.toLowerCase().includes(q)) return true;
  if (entry.notes?.toLowerCase().includes(q)) return true;
  if (entry.aliases?.some((a) => a.toLowerCase().includes(q))) return true;
  return false;
}

export function GlossaryPage() {
  const { documentId, edition } = useParams<{ documentId: string; edition: string }>();
  const [glossary, setGlossary] = useState<GlossaryPayloadV1 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!documentId || !edition) return;
    let stale = false;
    loadGlossary(documentId, edition)
      .then((data) => {
        if (!stale) setGlossary(data);
      })
      .catch((e) => {
        if (!stale) setError(e.message);
      });
    return () => {
      stale = true;
    };
  }, [documentId, edition]);

  const filtered = useMemo(() => {
    const entries = glossary?.entries ?? [];
    if (!query.trim()) return entries;
    return entries.filter((e) => matchesQuery(e, query.trim()));
  }, [glossary, query]);

  if (error) return <div role="alert">Error: {error}</div>;
  if (!glossary) return <div>Loading glossary...</div>;

  return (
    <article className="glossary-page">
      <header className="glossary-header">
        <Link to={`/documents/${documentId}/${edition}/p0001`} className="glossary-back-link">
          &larr; Reader
        </Link>
        <h1 className="glossary-title">Glossary</h1>
        <input
          className="glossary-search"
          type="search"
          placeholder="Search keywords..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="glossary-count">
          {filtered.length} of {glossary.entries?.length ?? 0} entries
        </span>
      </header>
      <section className="glossary-entries">
        {filtered.map((entry) => (
          <GlossaryEntryCard key={entry.concept_id} entry={entry} />
        ))}
        {filtered.length === 0 && <p className="glossary-empty">No matching entries.</p>}
      </section>
    </article>
  );
}
