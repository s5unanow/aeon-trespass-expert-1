import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { parseTocEntries } from '../../src/lib/render/toc';
import { TocBlock } from '../../src/components/reader/TocBlock';
import { BlockRenderer } from '../../src/components/reader/BlockRenderer';
import type { RenderBlock, RenderInlineNode } from '../../src/lib/render/types';

describe('parseTocEntries', () => {
  it('parses concatenated TOC text into entries', () => {
    const children: RenderInlineNode[] = [
      {
        kind: 'text',
        text: 'Introduction...............3Important Rules...........7',
        marks: [],
      },
    ];
    const result = parseTocEntries(children);
    expect(result).toEqual([
      { title: 'Introduction', pageNumber: '3' },
      { title: 'Important Rules', pageNumber: '7' },
    ]);
  });

  it('returns null for non-TOC text', () => {
    const children: RenderInlineNode[] = [
      { kind: 'text', text: 'Just a normal paragraph.', marks: [] },
    ];
    expect(parseTocEntries(children)).toBeNull();
  });

  it('returns null for a single dotted entry (needs >= 2)', () => {
    const children: RenderInlineNode[] = [
      { kind: 'text', text: 'Only one...............3', marks: [] },
    ];
    expect(parseTocEntries(children)).toBeNull();
  });

  it('handles Cyrillic text', () => {
    const children: RenderInlineNode[] = [
      {
        kind: 'text',
        text: 'Введение...............3Основы.........9',
        marks: [],
      },
    ];
    const result = parseTocEntries(children);
    expect(result).toHaveLength(2);
    expect(result![0].title).toBe('Введение');
    expect(result![1].title).toBe('Основы');
  });

  it('handles space before multi-digit page numbers', () => {
    const children: RenderInlineNode[] = [
      {
        kind: 'text',
        text: 'Introduction...............3 Voyage Phase........... 13 Battle Phase........... 33',
        marks: [],
      },
    ];
    const result = parseTocEntries(children);
    expect(result).toHaveLength(3);
    expect(result![1]).toEqual({ title: 'Voyage Phase', pageNumber: '13' });
    expect(result![2]).toEqual({ title: 'Battle Phase', pageNumber: '33' });
  });

  it('skips non-text inline nodes when flattening', () => {
    const children: RenderInlineNode[] = [
      { kind: 'text', text: 'A...............1', marks: [] },
      { kind: 'icon', symbol_id: 'sym.x', alt: 'x' },
      { kind: 'text', text: 'B...............2', marks: [] },
    ];
    const result = parseTocEntries(children);
    expect(result).toHaveLength(2);
  });
});

describe('TocBlock', () => {
  it('renders a nav with toc entries', () => {
    const entries = [
      { title: 'Chapter 1', pageNumber: '3' },
      { title: 'Chapter 2', pageNumber: '10' },
    ];
    render(<TocBlock id="toc-1" entries={entries} />);

    expect(screen.getByRole('navigation')).toBeDefined();
    expect(screen.getByText('Chapter 1')).toBeDefined();
    expect(screen.getByText('10')).toBeDefined();
  });
});

describe('BlockRenderer with TOC paragraph', () => {
  it('renders TOC paragraph as nav element', () => {
    const block: RenderBlock = {
      kind: 'paragraph',
      id: 'p0003.b001',
      children: [
        {
          kind: 'text',
          text: 'Intro...............3Rules...........7Basics.........9',
          marks: [],
        },
      ],
    };
    const { container } = render(<BlockRenderer block={block} />);
    expect(container.querySelector('nav.reader-toc')).not.toBeNull();
    expect(container.querySelectorAll('.reader-toc-entry')).toHaveLength(3);
  });
});
