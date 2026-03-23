import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { glossaryPayloadV1 } from '@atr/schemas';
import { loadGlossary } from '../lib/api/loadGlossary';

type GlossaryMap = Map<string, glossaryPayloadV1.GlossaryEntryV1>;

const GlossaryContext = createContext<GlossaryMap>(new Map());

interface GlossaryProviderProps {
  documentId: string;
  edition: string;
  children: ReactNode;
}

export function GlossaryProvider({ documentId, edition, children }: GlossaryProviderProps) {
  const [glossaryMap, setGlossaryMap] = useState<GlossaryMap>(new Map());

  useEffect(() => {
    let stale = false;
    loadGlossary(documentId, edition)
      .then((payload) => {
        if (stale) return;
        const map: GlossaryMap = new Map();
        for (const entry of payload.entries ?? []) {
          if (entry.icon_binding) {
            map.set(entry.icon_binding, entry);
          }
        }
        setGlossaryMap(map);
      })
      .catch((err: unknown) => {
        console.warn('Glossary load failed (non-blocking):', err);
      });
    return () => {
      stale = true;
    };
  }, [documentId, edition]);

  return <GlossaryContext value={glossaryMap}>{children}</GlossaryContext>;
}

export function useGlossary(): GlossaryMap {
  return useContext(GlossaryContext);
}
