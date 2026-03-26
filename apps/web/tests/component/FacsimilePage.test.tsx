import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { FacsimilePage } from '../../src/components/reader/FacsimilePage';
import type { RenderFacsimile } from '../../src/lib/render/types';

beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
});

afterEach(cleanup);

function makeFacsimile(annotationCount: number): RenderFacsimile {
  const annotations = Array.from({ length: annotationCount }, (_, i) => ({
    text: `EN text ${i + 1}`,
    translated_text: `RU text ${i + 1}`,
    bbox: { x0: 0.1 * i, y0: 0.1 * i, x1: 0.1 * i + 0.05, y1: 0.1 * i + 0.05 },
    kind: 'body' as const,
    priority: 0,
  }));
  return {
    raster_src: '/test-raster.png',
    raster_src_hires: '/test-raster-2x.png',
    width_px: 800,
    height_px: 1200,
    annotations,
  };
}

describe('FacsimilePage', () => {
  it('renders raster image with lazy fade-in class', () => {
    render(<FacsimilePage facsimile={makeFacsimile(0)} pageTitle="Cover" pageNumber={1} />);
    const img = screen.getByRole('img');
    expect(img.getAttribute('src')).toBe('/test-raster.png');
    expect(img.getAttribute('alt')).toBe('Page 1: Cover');
    expect(img.className).toContain('img-lazy');
    expect(img.className).not.toContain('is-loaded');
  });

  it('adds is-loaded class on image load', () => {
    render(<FacsimilePage facsimile={makeFacsimile(0)} pageTitle="Cover" pageNumber={1} />);
    const img = screen.getByRole('img');
    fireEvent.load(img);
    expect(img.className).toContain('is-loaded');
  });

  it('renders numbered markers for annotations', () => {
    render(<FacsimilePage facsimile={makeFacsimile(3)} pageTitle="Components" pageNumber={7} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    expect(markers).toHaveLength(3);
    expect(markers[0].textContent).toBe('1');
    expect(markers[1].textContent).toBe('2');
    expect(markers[2].textContent).toBe('3');
  });

  it('renders side panel with EN -> RU entries', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    const panel = screen.getByRole('list', { name: 'Annotations' });
    const items = within(panel).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    const buttons = within(panel).getAllByRole('button');
    expect(buttons).toHaveLength(2);
    expect(buttons[0].textContent).toContain('EN text 1');
    expect(buttons[0].textContent).toContain('RU text 1');
    expect(buttons[0].textContent).toContain('\u2192');
  });

  it('highlights marker and panel entry on marker click', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    fireEvent.click(markers[0]);
    expect(markers[0].className).toContain('is-active');
    const entries = within(screen.getByRole('list', { name: 'Annotations' })).getAllByRole(
      'button',
    );
    expect(entries[0].className).toContain('is-active');
  });

  it('toggles active state on second click', () => {
    render(<FacsimilePage facsimile={makeFacsimile(1)} pageTitle="Test" pageNumber={2} />);
    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });
    fireEvent.click(marker);
    expect(marker.className).toContain('is-active');
    fireEvent.click(marker);
    expect(marker.className).not.toContain('is-active');
  });

  it('highlights marker when panel entry is clicked', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    const entries = within(screen.getByRole('list', { name: 'Annotations' })).getAllByRole(
      'button',
    );
    fireEvent.click(entries[1]);
    expect(entries[1].className).toContain('is-active');
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    expect(markers[1].className).toContain('is-active');
  });

  it('sorts annotations in reading order (top-to-bottom)', () => {
    const facsimile: RenderFacsimile = {
      raster_src: '/test.png',
      width_px: 800,
      height_px: 1200,
      annotations: [
        {
          text: 'Bottom',
          translated_text: 'Низ',
          bbox: { x0: 0.1, y0: 0.8, x1: 0.3, y1: 0.9 },
          kind: 'body',
          priority: 0,
        },
        {
          text: 'Top',
          translated_text: 'Верх',
          bbox: { x0: 0.1, y0: 0.1, x1: 0.3, y1: 0.2 },
          kind: 'body',
          priority: 0,
        },
      ],
    };
    render(<FacsimilePage facsimile={facsimile} pageTitle="Test" pageNumber={1} />);
    const entries = within(screen.getByRole('list', { name: 'Annotations' })).getAllByRole(
      'button',
    );
    expect(entries[0].textContent).toContain('Top');
    expect(entries[1].textContent).toContain('Bottom');
  });

  it('shows only text when no translation exists', () => {
    const facsimile: RenderFacsimile = {
      raster_src: '/test.png',
      width_px: 800,
      height_px: 1200,
      annotations: [
        {
          text: 'English only',
          translated_text: '',
          bbox: { x0: 0.1, y0: 0.1, x1: 0.3, y1: 0.2 },
          kind: 'body',
          priority: 0,
        },
      ],
    };
    render(<FacsimilePage facsimile={facsimile} pageTitle="Test" pageNumber={1} />);
    const entry = within(screen.getByRole('list', { name: 'Annotations' })).getByRole('button');
    expect(entry.textContent).toContain('English only');
    expect(entry.textContent).not.toContain('\u2192');
  });

  it('renders no panel when annotations are empty', () => {
    render(<FacsimilePage facsimile={makeFacsimile(0)} pageTitle="Test" pageNumber={1} />);
    expect(screen.queryByRole('list', { name: 'Annotations' })).toBeNull();
  });

  it('renders toggle button with annotation count', () => {
    render(<FacsimilePage facsimile={makeFacsimile(5)} pageTitle="Test" pageNumber={1} />);
    const toggle = screen.getByRole('button', { name: /annotations/i });
    expect(toggle.textContent).toBe('Show annotations (5)');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('toggle button opens and closes the panel', () => {
    render(<FacsimilePage facsimile={makeFacsimile(3)} pageTitle="Test" pageNumber={1} />);
    const toggle = screen.getByRole('button', { name: /annotations/i });
    const panel = screen.getByRole('list', { name: 'Annotations' });

    expect(panel.className).not.toContain('is-open');
    expect(toggle.textContent).toBe('Show annotations (3)');

    fireEvent.click(toggle);
    expect(panel.className).toContain('is-open');
    expect(toggle.textContent).toBe('Hide annotations (3)');
    expect(toggle.getAttribute('aria-expanded')).toBe('true');

    fireEvent.click(toggle);
    expect(panel.className).not.toContain('is-open');
    expect(toggle.textContent).toBe('Show annotations (3)');
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
  });

  it('marker click opens the panel', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={1} />);
    const panel = screen.getByRole('list', { name: 'Annotations' });
    expect(panel.className).not.toContain('is-open');

    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });
    fireEvent.click(marker);
    expect(panel.className).toContain('is-open');
  });

  it('does not render toggle button when no annotations', () => {
    render(<FacsimilePage facsimile={makeFacsimile(0)} pageTitle="Test" pageNumber={1} />);
    expect(screen.queryByRole('button', { name: /annotations/i })).toBeNull();
  });
});
