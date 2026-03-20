import { useEffect, useState } from 'react';
import { loadManifest, type DocumentManifest } from '../lib/api/loadManifest';

interface ManifestWithEdition extends DocumentManifest {
  edition: string;
}

const DOCUMENTS = ['ato_core_v1_1', 'walking_skeleton'];
const EDITIONS = ['ru', 'en'];

/** Extract a human-readable page number from a page ID like "p0049" → "49". */
function formatPageNumber(pageId: string): string {
  const num = parseInt(pageId.replace(/^p/, ''), 10);
  return Number.isNaN(num) ? pageId : String(num);
}

export function DocumentIndexPage() {
  const [manifests, setManifests] = useState<ManifestWithEdition[]>([]);

  useEffect(() => {
    const fetches = DOCUMENTS.flatMap((docId) =>
      EDITIONS.map((edition) =>
        loadManifest(docId, edition)
          .then((data): ManifestWithEdition => ({ ...data, edition }))
          .catch(() => null),
      ),
    );
    Promise.all(fetches).then((results) => {
      const loaded = results.filter((m): m is ManifestWithEdition => m !== null);
      // Deduplicate: when both edition paths fall back to the same root
      // manifest, keep only the first (avoids identical duplicate sections)
      const seen = new Set<string>();
      const unique = loaded.filter((m) => {
        const key = `${m.document_id}:${m.pages.length}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      setManifests(unique);
    });
  }, []);

  return (
    <main style={{ maxWidth: 800, margin: '0 auto', padding: '2rem' }}>
      <h1>Aeon Trespass — Rules Reader</h1>
      {manifests.map((manifest) => (
        <section
          key={`${manifest.document_id}-${manifest.edition}`}
          style={{ marginBottom: '2rem' }}
        >
          <h2>
            {manifest.document_id} ({manifest.edition.toUpperCase()})
          </h2>
          <nav>
            <ul style={{ columns: 3, listStyle: 'none', padding: 0 }}>
              {manifest.pages.map((p) => (
                <li key={p.page_id} style={{ marginBottom: '0.25rem' }}>
                  <a
                    href={`/documents/${manifest.document_id}/${manifest.edition}/${p.page_id}`}
                  >
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
