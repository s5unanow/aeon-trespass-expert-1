import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BlockRenderer } from '../../src/components/reader/BlockRenderer';
import type { RenderBlock } from '../../src/lib/render/types';

describe('BlockRenderer', () => {
  it('renders a heading block', () => {
    const block: RenderBlock = {
      kind: 'heading',
      id: 'p0001.b001',
      level: 2,
      children: [{ kind: 'text', text: 'Проверка атаки', marks: [] }],
    };

    render(<BlockRenderer block={block} />);
    expect(screen.getByText('Проверка атаки')).toBeDefined();
  });

  it('renders a paragraph with text and icon', () => {
    const block: RenderBlock = {
      kind: 'paragraph',
      id: 'p0001.b002',
      children: [
        { kind: 'text', text: 'Получите 1 ', marks: [] },
        { kind: 'icon', symbol_id: 'sym.progress', alt: 'Прогресс' },
        { kind: 'text', text: ' Прогресс.', marks: [] },
      ],
    };

    render(<BlockRenderer block={block} />);
    expect(screen.getByText('Получите 1')).toBeDefined();
    expect(screen.getByText('Прогресс.')).toBeDefined();

    // Icon should be rendered with aria-label
    const icon = screen.getByRole('img', { name: 'Прогресс' });
    expect(icon).toBeDefined();
    expect(icon.getAttribute('data-symbol-id')).toBe('sym.progress');
  });

  it('renders a divider block', () => {
    const block: RenderBlock = { kind: 'divider', id: 'p0001.b003' };
    const { container } = render(<BlockRenderer block={block} />);
    expect(container.querySelector('hr')).toBeDefined();
  });
});
