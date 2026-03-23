import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router';
import { GlossaryPage } from '../../src/routes/GlossaryPage';
import type { glossaryPayloadV1 } from '@atr/schemas';

const sampleGlossary: glossaryPayloadV1.GlossaryPayloadV1 = {
  schema_version: 'glossary_payload.v1',
  document_id: 'test_doc',
  entries: [
    {
      concept_id: 'concept.danger',
      preferred_term: 'Опасность',
      source_term: 'Danger',
      aliases: ['Peril'],
      icon_binding: 'sym.danger',
      notes: 'Physical threat level',
      page_refs: [
        { page_id: 'p0010', source_page_number: 10 },
        { page_id: 'p0035', source_page_number: 35 },
      ],
    },
    {
      concept_id: 'concept.fate',
      preferred_term: 'Судьба',
      source_term: 'Fate',
      aliases: [],
      icon_binding: 'sym.fate',
      notes: 'Resource for rerolls',
      page_refs: [{ page_id: 'p0012', source_page_number: 12 }],
    },
    {
      concept_id: 'concept.voyage',
      preferred_term: 'Путешествие',
      source_term: 'Voyage Phase',
      aliases: ['Travel Phase'],
      icon_binding: null,
      notes: 'Overworld exploration phase',
      page_refs: [],
    },
  ],
};

function renderGlossary(path = '/documents/test_doc/ru/glossary') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/documents/:documentId/:edition/glossary" element={<GlossaryPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('GlossaryPage', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('renders all glossary entries', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByText('Опасность')).toBeDefined();
    });
    expect(screen.getByText('Судьба')).toBeDefined();
    expect(screen.getByText('Путешествие')).toBeDefined();
    expect(screen.getByText('3 of 3 entries')).toBeDefined();
  });

  it('filters entries by search query', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByText('Опасность')).toBeDefined();
    });

    const search = screen.getByPlaceholderText('Search keywords...');
    fireEvent.change(search, { target: { value: 'Danger' } });

    expect(screen.getByText('1 of 3 entries')).toBeDefined();
    expect(screen.getByText('Опасность')).toBeDefined();
    expect(screen.queryByText('Судьба')).toBeNull();
  });

  it('filters by alias text', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByText('Путешествие')).toBeDefined();
    });

    const search = screen.getByPlaceholderText('Search keywords...');
    fireEvent.change(search, { target: { value: 'Travel' } });

    expect(screen.getByText('1 of 3 entries')).toBeDefined();
    expect(screen.getByText('Путешествие')).toBeDefined();
  });

  it('shows empty state when no entries match', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByText('Опасность')).toBeDefined();
    });

    const search = screen.getByPlaceholderText('Search keywords...');
    fireEvent.change(search, { target: { value: 'zzzznotfound' } });

    expect(screen.getByText('No matching entries.')).toBeDefined();
    expect(screen.getByText('0 of 3 entries')).toBeDefined();
  });

  it('shows loading state before data arrives', () => {
    fetchSpy.mockReturnValue(new Promise(() => {}));
    renderGlossary();
    expect(screen.getByText('Loading glossary...')).toBeDefined();
  });

  it('shows error when fetch fails', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      status: 404,
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });
  });

  it('renders page reference links', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    renderGlossary();

    await waitFor(() => {
      expect(screen.getByText('Опасность')).toBeDefined();
    });

    const link10 = screen.getByText('10').closest('a');
    expect(link10?.getAttribute('href')).toBe('/documents/test_doc/ru/p0010');
    const link35 = screen.getByText('35').closest('a');
    expect(link35?.getAttribute('href')).toBe('/documents/test_doc/ru/p0035');
  });
});
