import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router';
import { EditionSwitcher } from '../../src/components/nav/EditionSwitcher';

function renderSwitcher(edition: string) {
  return render(
    <MemoryRouter>
      <EditionSwitcher documentId="ato_core_v1_1" pageId="p0015" currentEdition={edition} />
    </MemoryRouter>,
  );
}

describe('EditionSwitcher', () => {
  afterEach(() => {
    cleanup();
  });

  it('shows current edition as bold label', () => {
    renderSwitcher('ru');
    const active = screen.getByText('RU');
    expect(active.tagName).toBe('STRONG');
  });

  it('shows other edition as navigation link', () => {
    renderSwitcher('ru');
    const link = screen.getByText('EN').closest('a');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe('/documents/ato_core_v1_1/en/p0015');
  });

  it('preserves page id when switching to EN', () => {
    renderSwitcher('ru');
    const link = screen.getByText('EN').closest('a');
    expect(link?.getAttribute('href')).toContain('p0015');
  });

  it('preserves page id when switching to RU', () => {
    renderSwitcher('en');
    const link = screen.getByText('RU').closest('a');
    expect(link?.getAttribute('href')).toBe('/documents/ato_core_v1_1/ru/p0015');
  });

  it('has navigation role', () => {
    renderSwitcher('ru');
    expect(screen.getByRole('navigation', { name: /edition/i })).toBeDefined();
  });
});
