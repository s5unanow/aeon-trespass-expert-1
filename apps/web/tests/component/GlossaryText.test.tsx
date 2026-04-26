import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, afterEach, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { findKeywordHits, GlossaryText } from '../../src/components/reader/GlossaryText';
import { GlossaryProvider } from '../../src/contexts/GlossaryContext';
import { PageGlossaryProvider } from '../../src/contexts/PageContext';
import type { glossaryPayloadV1 } from '@atr/schemas';

const sampleGlossary: glossaryPayloadV1.GlossaryPayloadV1 = {
  schema_version: 'glossary_payload.v1',
  document_id: 'test_doc',
  entries: [
    {
      concept_id: 'concept.danger',
      preferred_term: 'Опасность',
      source_term: 'Danger',
      aliases: ['danger stat'],
      icon_binding: 'sym.danger',
      notes: 'Mortal axis stat',
    },
    {
      concept_id: 'concept.argo_knowledge',
      preferred_term: 'Знания Арго',
      source_term: 'Argo Knowledge',
      aliases: [],
      icon_binding: 'sym.argo_knowledge',
      notes: 'Argo stat',
    },
    {
      concept_id: 'concept.argo',
      preferred_term: 'Арго',
      source_term: 'Argo',
      aliases: [],
      icon_binding: null,
      notes: 'The ship',
    },
  ],
};

function LocationProbe() {
  const loc = useLocation();
  return (
    <div>
      <span data-testid="path">{loc.pathname}</span>
      <span data-testid="hash">{loc.hash}</span>
    </div>
  );
}

interface HarnessProps {
  text: string;
  mentions: string[];
  edition?: string;
}

function Harness({ text, mentions, edition = 'en' }: HarnessProps) {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(sampleGlossary),
  } as Response);
  // Spy stays alive for the test scope
  void fetchSpy;
  return (
    <MemoryRouter initialEntries={[`/documents/test_doc/${edition}/p0001`]}>
      <Routes>
        <Route
          path="/documents/:documentId/:edition/:pageId"
          element={
            <GlossaryProvider documentId="test_doc" edition={edition}>
              <PageGlossaryProvider mentions={mentions}>
                <p data-testid="paragraph">
                  <GlossaryText text={text} />
                </p>
              </PageGlossaryProvider>
              <LocationProbe />
            </GlossaryProvider>
          }
        />
        <Route path="/documents/:documentId/:edition/glossary" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('findKeywordHits (pure matcher)', () => {
  // Happy path: longest-first
  it('matches a single term inside a sentence (happy path)', () => {
    const hits = findKeywordHits('You take 1 Danger token.', [
      { surface: 'Danger', conceptId: 'concept.danger' },
    ]);
    expect(hits).toHaveLength(1);
    expect(hits[0]).toMatchObject({ surface: 'Danger', conceptId: 'concept.danger' });
  });

  // Failure input: substring of a longer word must NOT match
  it('does not match a surface form embedded in a longer word', () => {
    // "ger" inside "Danger" must not produce a hit; word boundaries enforced.
    const hits = findKeywordHits('Beware the dangerous voyager.', [
      { surface: 'Danger', conceptId: 'concept.danger' },
    ]);
    expect(hits).toHaveLength(0);
  });

  // Adversarial: longest-overlap wins
  it('longest match wins when surface forms overlap', () => {
    const hits = findKeywordHits('Spend 1 Argo Knowledge to reroll.', [
      { surface: 'Argo Knowledge', conceptId: 'concept.argo_knowledge' },
      { surface: 'Argo', conceptId: 'concept.argo' },
    ]);
    expect(hits).toHaveLength(1);
    expect(hits[0]).toMatchObject({
      surface: 'Argo Knowledge',
      conceptId: 'concept.argo_knowledge',
    });
  });

  it('matches multiple distinct terms in one string', () => {
    const hits = findKeywordHits('Roll Danger and gain Argo Knowledge.', [
      { surface: 'Argo Knowledge', conceptId: 'concept.argo_knowledge' },
      { surface: 'Danger', conceptId: 'concept.danger' },
    ]);
    expect(hits).toHaveLength(2);
    const ids = hits.map((h) => h.conceptId).sort();
    expect(ids).toEqual(['concept.argo_knowledge', 'concept.danger']);
  });

  it('respects unicode word boundaries (RU)', () => {
    // "Опасность" must NOT match inside "Безопасность" (which contains it).
    const hits = findKeywordHits('Безопасность важна.', [
      { surface: 'Опасность', conceptId: 'concept.danger' },
    ]);
    expect(hits).toHaveLength(0);
  });
});

describe('GlossaryText (component)', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('wraps a matched keyword as a clickable glossary link (EN edition)', async () => {
    render(<Harness text="You take 1 Danger token." mentions={['concept.danger']} edition="en" />);
    const link = await screen.findByRole('link');
    expect(link.textContent).toBe('Danger');
    expect(link.getAttribute('href')).toBe('/documents/test_doc/en/glossary#concept.danger');
    expect(link.getAttribute('data-concept-id')).toBe('concept.danger');
    expect(link.getAttribute('data-tooltip')).toBeTruthy();

    fireEvent.click(link);
    expect(screen.getByTestId('path').textContent).toBe('/documents/test_doc/en/glossary');
    expect(screen.getByTestId('hash').textContent).toBe('#concept.danger');
  });

  it('matches Cyrillic surface form on RU edition', async () => {
    render(<Harness text="Получите 1 Опасность." mentions={['concept.danger']} edition="ru" />);
    const link = await screen.findByRole('link');
    expect(link.textContent).toBe('Опасность');
    expect(link.getAttribute('href')).toBe('/documents/test_doc/ru/glossary#concept.danger');
  });

  it('renders plain text (no links) when no mention matches', async () => {
    render(
      <Harness text="Beware the dangerous voyager." mentions={['concept.danger']} edition="en" />,
    );
    // wait until glossary loads (so the matcher has had a chance to run)
    const para = await screen.findByTestId('paragraph');
    expect(para.querySelectorAll('a.glossary-keyword')).toHaveLength(0);
    expect(para.textContent).toBe('Beware the dangerous voyager.');
  });

  it('only emits one wrapping span when surface forms overlap (longest wins)', async () => {
    render(
      <Harness
        text="Spend 1 Argo Knowledge to reroll."
        mentions={['concept.argo_knowledge', 'concept.argo']}
        edition="en"
      />,
    );
    const links = await screen.findAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('data-concept-id')).toBe('concept.argo_knowledge');
    expect(links[0].textContent).toBe('Argo Knowledge');
  });

  it('skips concepts not listed in page mentions', async () => {
    render(
      <Harness
        text="You take 1 Danger token and meet the Argo."
        // Only concept.danger is mentioned on this page; "Argo" must stay plain.
        mentions={['concept.danger']}
        edition="en"
      />,
    );
    const links = await screen.findAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('data-concept-id')).toBe('concept.danger');
  });
});
