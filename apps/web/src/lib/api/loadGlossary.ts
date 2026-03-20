import type { GlossaryPayloadV1 } from '@atr/schemas';

export async function loadGlossary(
  documentId: string,
  edition: string = 'ru',
): Promise<GlossaryPayloadV1> {
  const url = `/documents/${documentId}/${edition}/data/glossary.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load glossary: ${res.status} ${url}`);
  }
  return res.json();
}
