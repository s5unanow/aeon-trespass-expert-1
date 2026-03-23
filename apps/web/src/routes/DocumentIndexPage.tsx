import { useEffect, useState } from 'react';
import { loadDocumentIndex } from '../lib/api/loadDocumentIndex';
import { loadManifest, type DocumentManifest } from '../lib/api/loadManifest';

interface ManifestWithEdition extends DocumentManifest {
  edition: string;
}

/** Hardcoded fallback when /documents/index.json is unavailable. */
const FALLBACK_DOCUMENTS = ['ato_core_v1_1', 'walking_skeleton'];
const FALLBACK_EDITIONS = ['ru', 'en'];

/** Extract a human-readable page number from a page ID like "p0049" → "49". */
function formatPageNumber(pageId: string): string {
  const num = parseInt(pageId.replace(/^p/, ''), 10);
  return Number.isNaN(num) ? pageId : String(num);
}

/** Build document/edition pairs — from index.json or hardcoded fallback. */
async function discoverDocuments(): Promise<{ docId: string; edition: string }[]> {
  const index = await loadDocumentIndex();
  if (index && index.documents.length > 0) {
    return index.documents.flatMap((doc) =>
      doc.editions.map((edition) => ({ docId: doc.document_id, edition })),
    );
  }
  // Fallback: try every combination
  return FALLBACK_DOCUMENTS.flatMap((docId) =>
    FALLBACK_EDITIONS.map((edition) => ({ docId, edition })),
  );
}

export function DocumentIndexPage() {
  const [manifests, setManifests] = useState<ManifestWithEdition[]>([]);

  useEffect(() => {
    discoverDocuments().then((pairs) => {
      const fetches = pairs.map(({ docId, edition }) =>
        loadManifest(docId, edition)
          .then((data): ManifestWithEdition => ({ ...data, edition }))
          .catch(() => null),
      );
      Promise.all(fetches).then((results) => {
        const loaded = results.filter((m): m is ManifestWithEdition => m !== null);
        // Deduplicate: when both edition paths fall back to the same root
        // manifest, keep only the first. Edition-specific manifests are always kept.
        const seen = new Set<string>();
        const unique = loaded.filter((m) => {
          if (m.edition_specific) return true;
          const key = `${m.document_id}:fallback`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        setManifests(unique);
      });
    });
  }, []);

  return (
    <main className="index-page">
      <h1>Aeon Trespass — Rules Reader</h1>
      {manifests.map((manifest) => (
        <section key={`${manifest.document_id}-${manifest.edition}`} className="index-section">
          <h2>
            {manifest.document_id} ({manifest.edition.toUpperCase()})
          </h2>
          <nav>
            <ul className="index-page-list">
              {manifest.pages.map((p) => (
                <li key={p.page_id}>
                  <a href={`/documents/${manifest.document_id}/${manifest.edition}/${p.page_id}`}>
                    {formatPageNumber(p.page_id)}
                    {p.title ? ` — ${p.title}` : ''}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </section>
      ))}
    </main>
  );
}
