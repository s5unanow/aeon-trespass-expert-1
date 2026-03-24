export interface DocumentManifest {
  document_id: string;
  pages: { page_id: string; title?: string; depth?: number }[];
  /** True when loaded from an edition-specific path (not a root fallback). */
  edition_specific?: boolean;
}

export async function loadManifest(
  documentId: string,
  edition: string = 'ru',
): Promise<DocumentManifest> {
  // Try edition-specific path first, fall back to root path
  const editionUrl = `/documents/${documentId}/${edition}/manifest.json`;
  const rootUrl = `/documents/${documentId}/manifest.json`;

  const editionRes = await fetch(editionUrl);
  if (editionRes.ok) {
    const data: DocumentManifest = await editionRes.json();
    return { ...data, edition_specific: true };
  }
  if (editionRes.status !== 404) {
    throw new Error(`Edition fetch failed: ${editionRes.status} ${editionUrl}`);
  }

  const rootRes = await fetch(rootUrl);
  if (rootRes.ok) {
    const data: DocumentManifest = await rootRes.json();
    return { ...data, edition_specific: false };
  }

  throw new Error(`Failed to load manifest: ${rootRes.status} ${rootUrl}`);
}
