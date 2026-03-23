import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';
import { GlossaryProvider, useGlossary } from '../../src/contexts/GlossaryContext';
import type { glossaryPayloadV1 } from '@atr/schemas';

const sampleGlossary: glossaryPayloadV1.GlossaryPayloadV1 = {
  schema_version: 'glossary_payload.v1',
  document_id: 'test_doc',
  entries: [
    {
      concept_id: 'concept.danger',
      preferred_term: 'Опасность',
      source_term: 'Danger',
      icon_binding: 'sym.danger',
      notes: 'Physical threat level',
    },
    {
      concept_id: 'concept.voyage',
      preferred_term: 'Путешествие',
      source_term: 'Voyage Phase',
      icon_binding: null,
      notes: 'No icon binding',
    },
  ],
};

function GlossaryConsumer() {
  const glossary = useGlossary();
  return (
    <div>
      <span data-testid="size">{glossary.size}</span>
      {glossary.has('sym.danger') && <span data-testid="danger">{glossary.get('sym.danger')!.preferred_term}</span>}
      {glossary.has('sym.voyage') && <span data-testid="voyage">found</span>}
    </div>
  );
}

describe('GlossaryContext', () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch');

  afterEach(() => {
    fetchSpy.mockReset();
    cleanup();
  });

  it('provides glossary entries keyed by icon_binding', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(sampleGlossary),
    } as Response);

    render(
      <GlossaryProvider documentId="test_doc" edition="ru">
        <GlossaryConsumer />
      </GlossaryProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('size').textContent).toBe('1');
    });
    expect(screen.getByTestId('danger').textContent).toBe('Опасность');
    // concept.voyage has no icon_binding, so it's excluded from the map
    expect(screen.queryByTestId('voyage')).toBeNull();
  });

  it('provides empty map when fetch fails', async () => {
    fetchSpy.mockRejectedValue(new Error('network error'));

    render(
      <GlossaryProvider documentId="test_doc" edition="ru">
        <GlossaryConsumer />
      </GlossaryProvider>,
    );

    // Map stays empty — no crash
    await waitFor(() => {
      expect(screen.getByTestId('size').textContent).toBe('0');
    });
  });

  it('provides empty map as default context', () => {
    // Without provider, useGlossary returns default empty map
    render(<GlossaryConsumer />);
    expect(screen.getByTestId('size').textContent).toBe('0');
  });
});
