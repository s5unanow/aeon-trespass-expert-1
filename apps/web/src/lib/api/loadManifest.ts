export interface DocumentManifest {
  document_id: string;
  pages: { page_id: string; title?: string }[];
}

export async function loadManifest(
  documentId: string,
  edition: string = 'ru',
): Promise<DocumentManifest> {
  const url = `/documents/${documentId}/${edition}/manifest.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load manifest: ${res.status} ${url}`);
  }
  return res.json();
}
