import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { IconInline } from '../../src/components/reader/IconInline';

describe('IconInline', () => {
  it('renders mapped icon as <img>', () => {
    render(<IconInline symbolId="sym.progress" alt="Progress" />);
    const img = screen.getByRole('img', { name: 'Progress' });
    expect(img.tagName).toBe('IMG');
    expect(img.getAttribute('src')).toBe('/icons/stat_progress.png');
    expect(img.getAttribute('data-symbol-id')).toBe('sym.progress');
  });

  it('renders unmapped icon as fallback <span>', () => {
    render(<IconInline symbolId="sym.unknown_thing" />);
    const span = screen.getByRole('img', { name: 'unknown_thing' });
    expect(span.tagName).toBe('SPAN');
    expect(span.textContent).toBe('[unknown_thing]');
    expect(span.getAttribute('data-symbol-id')).toBe('sym.unknown_thing');
  });

  it('returns null for hidden decorative icons', () => {
    const { container } = render(<IconInline symbolId="sym.board_tile_a" />);
    expect(container.innerHTML).toBe('');
  });

  it('uses alt prop when provided', () => {
    render(<IconInline symbolId="sym.danger" alt="Опасность" />);
    const img = screen.getByRole('img', { name: 'Опасность' });
    expect(img.getAttribute('alt')).toBe('Опасность');
  });

  it('falls back to symbolId for label when no alt', () => {
    render(<IconInline symbolId="sym.fate" />);
    const img = screen.getByRole('img', { name: 'fate' });
    expect(img.getAttribute('alt')).toBe('fate');
  });
});
