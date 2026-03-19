import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BlockRenderer } from '../../src/components/reader/BlockRenderer';
import { InlineRenderer } from '../../src/components/reader/InlineRenderer';
import type { RenderBlock, RenderInlineNode } from '../../src/lib/render/types';

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

  it('renders a list_item block', () => {
    const block: RenderBlock = {
      kind: 'list_item',
      id: 'p0001.b004',
      children: [{ kind: 'text', text: 'Первый пункт', marks: [] }],
    };

    const { container } = render(<BlockRenderer block={block} />);
    const li = container.querySelector('li');
    expect(li).toBeDefined();
    expect(li?.id).toBe('p0001.b004');
    expect(li?.className).toBe('reader-list-item');
    expect(screen.getByText('Первый пункт')).toBeDefined();
  });

  it('renders a callout block', () => {
    const block: RenderBlock = {
      kind: 'callout',
      id: 'p0001.b005',
      variant: 'warning',
      children: [{ kind: 'text', text: 'Внимание!', marks: [] }],
    };

    const { container } = render(<BlockRenderer block={block} />);
    const aside = container.querySelector('aside');
    expect(aside).toBeDefined();
    expect(aside?.id).toBe('p0001.b005');
    expect(aside?.className).toBe('reader-callout');
    expect(aside?.dataset.variant).toBe('warning');
    expect(screen.getByText('Внимание!')).toBeDefined();
  });

  it('renders a table block', () => {
    const block: RenderBlock = {
      kind: 'table',
      id: 'p0001.b006',
      children: [{ kind: 'text', text: 'Ячейка', marks: [] }],
    };

    const { container } = render(<BlockRenderer block={block} />);
    const table = container.querySelector('[role="table"]');
    expect(table).toBeDefined();
    expect(table?.id).toBe('p0001.b006');
    expect(table?.className).toBe('reader-table');
    expect(screen.getByText('Ячейка')).toBeDefined();
  });

  it('renders unsupported block kind with visible error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const block = { kind: 'unknown_kind', id: 'p0001.b007' } as unknown as RenderBlock;

    const { container } = render(<BlockRenderer block={block} />);
    const errorDiv = container.querySelector('.reader-unsupported-block');
    expect(errorDiv).toBeDefined();
    expect(errorDiv?.textContent).toContain('[Unsupported block]');
    expect(spy).toHaveBeenCalledWith('Unsupported block kind:', 'unknown_kind');
    spy.mockRestore();
  });
});

describe('InlineRenderer', () => {
  it('renders unsupported inline kind with visible error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const node = { kind: 'unknown_inline' } as unknown as RenderInlineNode;

    const { container } = render(<InlineRenderer node={node} />);
    const errorSpan = container.querySelector('.reader-unsupported-inline');
    expect(errorSpan).toBeDefined();
    expect(errorSpan?.textContent).toContain('[?]');
    expect(spy).toHaveBeenCalledWith('Unsupported inline kind:', 'unknown_inline');
    spy.mockRestore();
  });
});
