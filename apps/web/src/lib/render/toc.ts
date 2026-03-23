import type { RenderInlineNode } from './types';

export interface TocEntry {
  title: string;
  pageNumber: string;
}

/** Minimum dot-leader count to recognise a TOC line. */
const MIN_DOTS = 3;
/** Minimum entries needed to classify a paragraph as TOC. */
const MIN_ENTRIES = 2;

/** Extract plain text from a list of inline nodes. */
function flattenInlines(nodes: RenderInlineNode[]): string {
  return nodes
    .map((n) => {
      if (n.kind === 'text') return n.text;
      if (n.kind === 'icon') return n.alt ?? '';
      return '';
    })
    .join('');
}

/** Parse TOC entries from concatenated text. Returns null if not a TOC. */
export function parseTocEntries(children: RenderInlineNode[]): TocEntry[] | null {
  const raw = flattenInlines(children);
  if (raw.length === 0) return null;

  // Quick guard: need at least MIN_DOTS consecutive dots somewhere
  if (!raw.includes('.'.repeat(MIN_DOTS))) return null;

  const re = /(.+?)\.{3,}\s*(\d+)/g;
  const entries: TocEntry[] = [];
  let match: RegExpExecArray | null;

  while ((match = re.exec(raw)) !== null) {
    entries.push({
      title: match[1].trim(),
      pageNumber: match[2],
    });
  }

  return entries.length >= MIN_ENTRIES ? entries : null;
}
