import { useEffect, useState } from 'react';

interface PageEntry {
  page_id: string;
  title: string;
}

interface Manifest {
  document_id: string;
  edition: string;
  pages: PageEntry[];
}

const DOCUMENTS = ['ato_core_v1_1', 'walking_skeleton'];
const EDITIONS = ['ru', 'en'];

export function DocumentIndexPage() {
  const [manifests, setManifests] = useState<Manifest[]>([]);

  useEffect(() => {
    const fetches = DOCUMENTS.flatMap((docId) =>
      EDITIONS.map((edition) =>
        fetch(`/documents/${docId}/${edition}/manifest.json`)
          .then((r) => (r.ok ? r.json() : null))
          .then((data) => (data ? { ...data, edition } : null))
          .catch(() => null),
      ),
    );
    Promise.all(fetches).then((results) =>
      setManifests(results.filter((m): m is Manifest => m !== null)),
    );
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
                    {p.page_id.replace('p0', 'p').replace('p0', '')}
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
