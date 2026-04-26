import { useEffect, useMemo, useState } from 'react';
import { useLocation, useParams } from 'react-router';
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
  const location = useLocation();
  const targetConceptId = location.hash ? location.hash.slice(1) : '';

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

  // After data loads, scroll the deep-link target into view. Search filtering
  // may hide the target; we only act when the target element is present.
  // `scrollIntoView` is jsdom-flaky — guard it. We deliberately rely on the
  // `glossary-card-highlight` class (from `highlighted` prop below) rather
  // than CSS `:target`, so we don't need to re-bounce the hash to force a
  // pseudo-class match — that bounce inserted spurious history entries and
  // broke browser-back. See S5U-584.
  useEffect(() => {
    if (!glossary || !targetConceptId) return;
    const el = document.getElementById(targetConceptId);
    if (!el) return;
    if (typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
  }, [glossary, targetConceptId, query]);

  const filtered = useMemo(() => {
    const entries = glossary?.entries ?? [];
    if (!query.trim()) return entries;
    return entries.filter((e) => matchesQuery(e, query.trim()));
  }, [glossary, query]);

  if (error) return <div role="alert">Error: {error}</div>;
  if (!glossary) {
    return (
      <div className="skeleton" aria-busy="true" aria-label="Loading glossary">
        <div className="skeleton-bone skeleton-heading" />
        <div className="skeleton-bone skeleton-block" />
        <div className="skeleton-bone skeleton-block" />
        <div className="skeleton-bone skeleton-block" />
      </div>
    );
  }

  return (
    <article className="glossary-page fade-in">
      <header className="glossary-header">
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
          <GlossaryEntryCard
            key={entry.concept_id}
            entry={entry}
            highlighted={entry.concept_id === targetConceptId}
          />
        ))}
        {filtered.length === 0 && <p className="glossary-empty">No matching entries.</p>}
      </section>
    </article>
  );
}
