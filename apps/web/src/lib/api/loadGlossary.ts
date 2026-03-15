export interface GlossaryEntry {
  concept_id: string;
  preferred_term: string;
  source_term: string;
  aliases: string[];
  icon_binding: string | null;
  notes: string;
}

export interface GlossaryPayload {
  document_id: string;
  entries: GlossaryEntry[];
}

export async function loadGlossary(documentId: string): Promise<GlossaryPayload> {
  const url = `/documents/${documentId}/data/glossary.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load glossary: ${res.status} ${url}`);
  }
  return res.json();
}
