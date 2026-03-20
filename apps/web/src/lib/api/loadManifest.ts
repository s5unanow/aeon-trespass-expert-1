export interface DocumentManifest {
  document_id: string;
  pages: { page_id: string; title?: string }[];
}

export async function loadManifest(
  documentId: string,
  edition: string = 'ru',
): Promise<DocumentManifest> {
  // Try edition-specific path first, fall back to root path
  const editionUrl = `/documents/${documentId}/${edition}/manifest.json`;
  const rootUrl = `/documents/${documentId}/manifest.json`;

  const editionRes = await fetch(editionUrl);
  if (editionRes.ok) return editionRes.json();

  const rootRes = await fetch(rootUrl);
  if (rootRes.ok) return rootRes.json();

  throw new Error(`Failed to load manifest: ${rootRes.status} ${rootUrl}`);
}
