import { useEffect, useState } from 'react';

interface PageEntry {
  page_id: string;
  title: string;
}

interface Manifest {
  document_id: string;
  pages: PageEntry[];
}

const DOCUMENTS = ['ato_core_v1_1', 'walking_skeleton'];

export function DocumentIndexPage() {
  const [manifests, setManifests] = useState<Manifest[]>([]);

  useEffect(() => {
    Promise.all(
      DOCUMENTS.map((docId) =>
        fetch(`/documents/${docId}/manifest.json`)
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
      ),
    ).then((results) =>
      setManifests(results.filter((m): m is Manifest => m !== null)),
    );
  }, []);

  return (
    <main style={{ maxWidth: 800, margin: '0 auto', padding: '2rem' }}>
      <h1>Aeon Trespass — Rules Reader</h1>
      {manifests.map((manifest) => (
        <section key={manifest.document_id} style={{ marginBottom: '2rem' }}>
          <h2>{manifest.document_id}</h2>
          <nav>
            <ul style={{ columns: 3, listStyle: 'none', padding: 0 }}>
              {manifest.pages.map((p) => (
                <li key={p.page_id} style={{ marginBottom: '0.25rem' }}>
                  <a href={`/documents/${manifest.document_id}/${p.page_id}`}>
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
