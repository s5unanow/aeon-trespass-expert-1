import { useMemo, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';
import type { GlossaryEntry } from '../../contexts/GlossaryContext';
import { useGlossaryShape } from '../../contexts/GlossaryContext';
import { usePageGlossaryMentions } from '../../contexts/PageContext';

interface GlossaryTextProps {
  text: string;
  marks?: string[];
}

/**
 * A surface-form pattern: literal phrase + concept_id.
 * The matcher is case-insensitive and word-boundary-aware (Unicode-friendly).
 */
interface SurfacePattern {
  surface: string;
  conceptId: string;
}

interface Hit {
  start: number;
  end: number;
  surface: string;
  conceptId: string;
}

/**
 * Word boundary regex that works for non-ASCII (cyrillic) — `\b` in JS
 * matches only ASCII word boundaries, which would let `"Опасность"` match
 * inside `"Безопасность"`. We use lookarounds + a permissive word-char class
 * built from common letter ranges + apostrophe + dash.
 */
const WORD_CHAR = '[A-Za-z\\u00C0-\\u024F\\u0400-\\u04FF\\u0500-\\u052F0-9_]';

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function makePattern(surface: string): RegExp {
  return new RegExp(
    `(?<!${WORD_CHAR})${escapeRegExp(surface)}(?!${WORD_CHAR})`,
    'gi',
  );
}

/**
 * Pick the surface forms for an entry suitable for the active edition.
 *
 * - RU edition: prefer `preferred_term` (RU) + aliases.
 * - EN edition (or unknown): prefer `source_term` (EN) + aliases.
 *
 * Aliases are included unconditionally because authored aliases are language-
 * specific in practice (`"danger stat"` is EN, `"Опасность"` is RU); the
 * page text language is what filters them naturally — only same-language
 * aliases will substring-match the page text.
 */
function surfaceFormsFor(entry: GlossaryEntry, edition: string): string[] {
  const forms: string[] = [];
  const isRu = edition === 'ru';
  const primary = isRu ? entry.preferred_term : entry.source_term;
  const secondary = isRu ? entry.source_term : entry.preferred_term;
  if (primary) forms.push(primary);
  if (secondary) forms.push(secondary);
  for (const a of entry.aliases ?? []) {
    if (a) forms.push(a);
  }
  // De-dup while preserving order (longer first).
  const seen = new Set<string>();
  return forms
    .filter((f) => {
      const k = f.toLowerCase();
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .sort((a, b) => b.length - a.length);
}

/**
 * Build a pattern table for the specific concepts mentioned on this page.
 * O(mentions × surface_forms) at render time, but `mentions.length` is
 * typically <30 and each entry has <5 forms, so this is trivial.
 */
function buildPatterns(
  mentions: readonly string[],
  byConcept: Map<string, GlossaryEntry>,
  edition: string,
): SurfacePattern[] {
  const patterns: SurfacePattern[] = [];
  for (const conceptId of mentions) {
    const entry = byConcept.get(conceptId);
    if (!entry) continue;
    for (const surface of surfaceFormsFor(entry, edition)) {
      patterns.push({ surface, conceptId });
    }
  }
  // Sort by surface length DESC so longer phrases win in the longest-first
  // greedy span allocation.
  patterns.sort((a, b) => b.surface.length - a.surface.length);
  return patterns;
}

/**
 * Find non-overlapping hits in `text`. Longest-first greedy: longer surface
 * forms claim their span before shorter ones can overlap. Identical-length
 * ties are resolved by earlier position.
 */
export function findKeywordHits(text: string, patterns: SurfacePattern[]): Hit[] {
  if (!text || patterns.length === 0) return [];
  const candidates: Hit[] = [];
  for (const p of patterns) {
    const re = makePattern(p.surface);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      candidates.push({
        start: m.index,
        end: m.index + m[0].length,
        surface: m[0],
        conceptId: p.conceptId,
      });
      if (m.index === re.lastIndex) re.lastIndex++; // safeguard against zero-width
    }
  }
  // Longest-first sort; on ties, earlier start wins.
  candidates.sort((a, b) => {
    const lenDiff = b.end - b.start - (a.end - a.start);
    if (lenDiff !== 0) return lenDiff;
    return a.start - b.start;
  });
  const claimed: Hit[] = [];
  for (const h of candidates) {
    const overlaps = claimed.some((c) => h.start < c.end && h.end > c.start);
    if (!overlaps) claimed.push(h);
  }
  // Return in source order so we can splice contiguously.
  claimed.sort((a, b) => a.start - b.start);
  return claimed;
}

/**
 * Render a string with marks (bold/italic). Mirrors `wrapMarks` in
 * `InlineRenderer.tsx` so a highlighted keyword inside a bold paragraph
 * stays bold.
 */
function applyMarks(node: ReactNode, marks?: string[]): ReactNode {
  let result = node;
  if (marks?.includes('bold')) {
    result = <strong>{result}</strong>;
  }
  if (marks?.includes('italic')) {
    result = <em>{result}</em>;
  }
  return result;
}

export function GlossaryText({ text, marks }: GlossaryTextProps) {
  const { byConcept, edition } = useGlossaryShape();
  const mentions = usePageGlossaryMentions();
  const navigate = useNavigate();
  const { documentId, edition: routeEdition } = useParams<{
    documentId: string;
    edition: string;
  }>();

  const patterns = useMemo(
    () => buildPatterns(mentions, byConcept, edition || routeEdition || ''),
    [mentions, byConcept, edition, routeEdition],
  );

  const hits = useMemo(() => findKeywordHits(text, patterns), [text, patterns]);

  if (hits.length === 0 || !documentId || !routeEdition) {
    return <span>{applyMarks(text, marks)}</span>;
  }

  const segments: ReactNode[] = [];
  let cursor = 0;
  hits.forEach((hit, idx) => {
    if (hit.start > cursor) {
      segments.push(text.slice(cursor, hit.start));
    }
    const entry = byConcept.get(hit.conceptId);
    const tooltip = entry
      ? entry.source_term && entry.preferred_term && entry.source_term !== entry.preferred_term
        ? `${entry.source_term} — ${entry.notes || entry.preferred_term}`
        : (entry.notes || entry.preferred_term || entry.source_term)
      : undefined;
    const href = `/documents/${documentId}/${routeEdition}/glossary#${hit.conceptId}`;
    segments.push(
      <a
        key={`kw-${idx}-${hit.start}`}
        className="glossary-keyword glossary-tooltip"
        data-tooltip={tooltip}
        data-concept-id={hit.conceptId}
        href={href}
        onClick={(e) => {
          e.preventDefault();
          navigate(href);
        }}
      >
        {hit.surface}
      </a>,
    );
    cursor = hit.end;
  });
  if (cursor < text.length) {
    segments.push(text.slice(cursor));
  }

  return <span>{applyMarks(<>{segments}</>, marks)}</span>;
}
