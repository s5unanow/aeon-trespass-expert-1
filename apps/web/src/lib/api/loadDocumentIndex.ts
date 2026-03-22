export interface DocumentIndexEntry {
  document_id: string;
  editions: string[];
}

export interface DocumentIndex {
  documents: DocumentIndexEntry[];
}

/**
 * Fetch /documents/index.json.
 * Returns null if the index is unavailable (404, network error, etc.).
 */
export async function loadDocumentIndex(): Promise<DocumentIndex | null> {
  try {
    const res = await fetch('/documents/index.json');
    if (!res.ok) return null;
    return (await res.json()) as DocumentIndex;
  } catch {
    return null;
  }
}
