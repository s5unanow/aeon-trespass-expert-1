import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { IconInline } from '../../src/components/reader/IconInline';
import { GlossaryProvider } from '../../src/contexts/GlossaryContext';
import type { glossaryPayloadV1 } from '@atr/schemas';
import { vi } from 'vitest';

describe('IconInline', () => {
  it('renders mapped icon as <img>', () => {
    render(
      <MemoryRouter>
        <IconInline symbolId="sym.progress" alt="Progress" />
      </MemoryRouter>,
    );
    const img = screen.getByRole('img', { name: 'Progress' });
    expect(img.tagName).toBe('IMG');
    expect(img.getAttribute('src')).toBe('/icons/stat_progress.png');
    expect(img.getAttribute('data-symbol-id')).toBe('sym.progress');
  });

  it('renders unmapped icon as fallback <span>', () => {
    render(
      <MemoryRouter>
        <IconInline symbolId="sym.unknown_thing" />
      </MemoryRouter>,
    );
    const span = screen.getByRole('img', { name: 'unknown_thing' });
    expect(span.tagName).toBe('SPAN');
    expect(span.textContent).toBe('[unknown_thing]');
    expect(span.getAttribute('data-symbol-id')).toBe('sym.unknown_thing');
  });

  it('returns null for hidden decorative icons', () => {
    const { container } = render(
      <MemoryRouter>
        <IconInline symbolId="sym.board_tile_a" />
      </MemoryRouter>,
    );
    expect(container.innerHTML).toBe('');
  });

  it('uses alt prop when provided', () => {
    render(
      <MemoryRouter>
        <IconInline symbolId="sym.danger" alt="Опасность" />
      </MemoryRouter>,
    );
    const img = screen.getByRole('img', { name: 'Опасность' });
    expect(img.getAttribute('alt')).toBe('Опасность');
  });

  it('falls back to symbolId for label when no alt', () => {
    render(
      <MemoryRouter>
        <IconInline symbolId="sym.fate" />
      </MemoryRouter>,
    );
    const img = screen.getByRole('img', { name: 'fate' });
    expect(img.getAttribute('alt')).toBe('fate');
  });

  // --- S5U-584: click navigates to /glossary#<concept_id> ---

  const testGlossary: glossaryPayloadV1.GlossaryPayloadV1 = {
    schema_version: 'glossary_payload.v1',
    document_id: 'test_doc',
    entries: [
      {
        concept_id: 'concept.danger',
        preferred_term: 'Опасность',
        source_term: 'Danger',
        icon_binding: 'sym.danger',
        notes: 'Threat level',
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

  it('clicking a mapped icon with a glossary entry navigates to glossary deep-link', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(testGlossary),
    } as Response);

    render(
      <MemoryRouter initialEntries={['/documents/test_doc/ru/p0001']}>
        <Routes>
          <Route
            path="/documents/:documentId/:edition/:pageId"
            element={
              <GlossaryProvider documentId="test_doc" edition="ru">
                <IconInline symbolId="sym.danger" alt="Danger" />
                <LocationProbe />
              </GlossaryProvider>
            }
          />
          <Route
            path="/documents/:documentId/:edition/glossary"
            element={<LocationProbe />}
          />
        </Routes>
      </MemoryRouter>,
    );

    // Wait for glossary to load + role flip from img -> link wrapper
    await screen.findByRole('link');

    const wrapper = screen.getByRole('link');
    fireEvent.click(wrapper);

    expect(screen.getByTestId('path').textContent).toBe('/documents/test_doc/ru/glossary');
    expect(screen.getByTestId('hash').textContent).toBe('#concept.danger');

    fetchSpy.mockRestore();
  });

  it('icon without a glossary entry does not become a link', () => {
    // No GlossaryProvider -> empty map -> no entry -> not navigable
    render(
      <MemoryRouter>
        <IconInline symbolId="sym.priority_target" alt="Priority Target" />
      </MemoryRouter>,
    );
    expect(screen.queryByRole('link')).toBeNull();
    // Still renders the img
    expect(screen.getByRole('img', { name: 'Priority Target' })).toBeDefined();
  });
});
