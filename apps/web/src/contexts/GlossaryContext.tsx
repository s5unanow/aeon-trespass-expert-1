import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { glossaryPayloadV1 } from '@atr/schemas';
import { loadGlossary } from '../lib/api/loadGlossary';

export type GlossaryEntry = glossaryPayloadV1.GlossaryEntryV1;

/**
 * Glossary lookup surface.
 *
 * - `byIcon`: maps `sym.<id>` -> entry, used by `IconInline`'s tooltip + click.
 * - `byConcept`: maps `concept.<id>` -> entry, used by `GlossaryText` and the
 *   glossary deep-link target.
 * - `entries`: flat list, used to materialize per-page surface-form patterns.
 * - `edition`: the active edition (`"ru"` or `"en"`), so the matcher can prefer
 *   the right surface forms (RU page -> `preferred_term + aliases`,
 *   EN page -> `source_term + aliases`).
 */
export interface GlossaryShape {
  byIcon: Map<string, GlossaryEntry>;
  byConcept: Map<string, GlossaryEntry>;
  entries: readonly GlossaryEntry[];
  edition: string;
}

const EMPTY_SHAPE: GlossaryShape = {
  byIcon: new Map(),
  byConcept: new Map(),
  entries: [],
  edition: '',
};

const GlossaryContext = createContext<GlossaryShape>(EMPTY_SHAPE);

interface GlossaryProviderProps {
  documentId: string;
  edition: string;
  children: ReactNode;
}

export function GlossaryProvider({ documentId, edition, children }: GlossaryProviderProps) {
  const [entries, setEntries] = useState<readonly GlossaryEntry[]>([]);

  useEffect(() => {
    let stale = false;
    loadGlossary(documentId, edition)
      .then((payload) => {
        if (stale) return;
        setEntries(payload.entries ?? []);
      })
      .catch((err: unknown) => {
        console.warn('Glossary load failed (non-blocking):', err);
      });
    return () => {
      stale = true;
    };
  }, [documentId, edition]);

  const shape = useMemo<GlossaryShape>(() => {
    const byIcon = new Map<string, GlossaryEntry>();
    const byConcept = new Map<string, GlossaryEntry>();
    for (const entry of entries) {
      if (entry.icon_binding) {
        byIcon.set(entry.icon_binding, entry);
      }
      byConcept.set(entry.concept_id, entry);
    }
    return { byIcon, byConcept, entries, edition };
  }, [entries, edition]);

  return <GlossaryContext value={shape}>{children}</GlossaryContext>;
}

/**
 * Returns the `Map<symbolId, GlossaryEntry>` surface for backwards
 * compatibility with `IconInline`. New consumers should call
 * `useGlossaryShape()`.
 */
export function useGlossary(): Map<string, GlossaryEntry> {
  return useContext(GlossaryContext).byIcon;
}

/** Full glossary shape — entries, both indexes, and edition. */
export function useGlossaryShape(): GlossaryShape {
  return useContext(GlossaryContext);
}
