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

/** Format a document ID into a human-readable title. */
function formatDocumentTitle(docId: string): string {
  return docId
    .replace(/_v(\d+)_(\d+)$/, ' v$1.$2')
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => (/^v\d/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(' ');
}

/** Build document/edition pairs — from index.json or hardcoded fallback. */
async function discoverDocuments(): Promise<{ docId: string; edition: string }[]> {
  const index = await loadDocumentIndex();
  if (index && index.documents.length > 0) {
    return index.documents.flatMap((doc) =>
      doc.editions.map((edition) => ({ docId: doc.document_id, edition })),
    );
  }
  return FALLBACK_DOCUMENTS.flatMap((docId) =>
    FALLBACK_EDITIONS.map((edition) => ({ docId, edition })),
  );
}

export function DocumentIndexPage() {
  const [manifests, setManifests] = useState<ManifestWithEdition[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    discoverDocuments()
      .then((pairs) => {
        const fetches = pairs.map(({ docId, edition }) =>
          loadManifest(docId, edition)
            .then((data): ManifestWithEdition => ({ ...data, edition }))
            .catch(() => null),
        );
        return Promise.all(fetches);
      })
      .then((results) => {
        const loaded = results.filter((m): m is ManifestWithEdition => m !== null);
        const seen = new Set<string>();
        const unique = loaded.filter((m) => {
          if (m.edition_specific) return true;
          const key = `${m.document_id}:fallback`;
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        setManifests(unique);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <main className="index-page">
      <header className="index-hero">
        <h1 className="index-hero-title">Aeon Trespass</h1>
        <p className="index-hero-subtitle">Rules Reader</p>
      </header>

      {loading ? (
        <p className="index-loading">Loading documents…</p>
      ) : manifests.length === 0 ? (
        <p className="index-empty">No documents found</p>
      ) : (
        <div className="index-cards">
          {manifests.map((manifest) => (
            <article key={`${manifest.document_id}-${manifest.edition}`} className="doc-card">
              <div className="doc-card-header">
                <h2 className="doc-card-title">{formatDocumentTitle(manifest.document_id)}</h2>
                <span className="doc-card-edition">{manifest.edition.toUpperCase()}</span>
              </div>
              <p className="doc-card-meta">
                {manifest.pages.length} {manifest.pages.length === 1 ? 'page' : 'pages'}
              </p>
              <nav
                className="page-grid"
                aria-label={`Pages for ${formatDocumentTitle(manifest.document_id)} ${manifest.edition.toUpperCase()}`}
              >
                {manifest.pages.map((p) => (
                  <a
                    key={p.page_id}
                    href={`/documents/${manifest.document_id}/${manifest.edition}/${p.page_id}`}
                    className="page-pill"
                    title={p.title || `Page ${formatPageNumber(p.page_id)}`}
                  >
                    {formatPageNumber(p.page_id)}
                  </a>
                ))}
              </nav>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
