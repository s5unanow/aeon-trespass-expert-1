import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { FacsimilePage } from '../../src/components/reader/FacsimilePage';
import type { RenderFacsimile } from '../../src/lib/render/types';

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

  it('shows tooltip with EN → RU text on marker click', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    expect(screen.queryByRole('tooltip')).toBeNull();

    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    fireEvent.click(markers[0]);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip.textContent).toContain('EN text 1');
    expect(tooltip.textContent).toContain('\u2192');
    expect(tooltip.textContent).toContain('RU text 1');
  });

  it('highlights marker when tooltip is shown', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    fireEvent.click(markers[0]);
    expect(markers[0].className).toContain('is-active');
    expect(markers[0].getAttribute('aria-describedby')).toBe('facsimile-tooltip');
  });

  it('dismisses tooltip on second click of same marker', () => {
    render(<FacsimilePage facsimile={makeFacsimile(1)} pageTitle="Test" pageNumber={2} />);
    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });

    fireEvent.click(marker);
    expect(screen.getByRole('tooltip')).toBeTruthy();
    expect(marker.className).toContain('is-active');

    fireEvent.click(marker);
    expect(screen.queryByRole('tooltip')).toBeNull();
    expect(marker.className).not.toContain('is-active');
  });

  it('switches tooltip when different marker is clicked', () => {
    render(<FacsimilePage facsimile={makeFacsimile(2)} pageTitle="Test" pageNumber={2} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });

    fireEvent.click(markers[0]);
    expect(screen.getByRole('tooltip').textContent).toContain('EN text 1');

    fireEvent.click(markers[1]);
    expect(screen.getByRole('tooltip').textContent).toContain('EN text 2');
    expect(markers[0].className).not.toContain('is-active');
    expect(markers[1].className).toContain('is-active');
  });

  it('dismisses tooltip on click outside', () => {
    render(<FacsimilePage facsimile={makeFacsimile(1)} pageTitle="Test" pageNumber={2} />);
    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });

    fireEvent.click(marker);
    expect(screen.getByRole('tooltip')).toBeTruthy();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('dismisses tooltip on Escape key', () => {
    render(<FacsimilePage facsimile={makeFacsimile(1)} pageTitle="Test" pageNumber={2} />);
    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });

    fireEvent.click(marker);
    expect(screen.getByRole('tooltip')).toBeTruthy();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).toBeNull();
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
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    expect(markers[0].getAttribute('aria-label')).toBe('Annotation 1: Верх');
    expect(markers[1].getAttribute('aria-label')).toBe('Annotation 2: Низ');
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
    const marker = screen.getByRole('button', { name: /^Annotation 1:/ });
    fireEvent.click(marker);

    const tooltip = screen.getByRole('tooltip');
    expect(tooltip.textContent).toContain('English only');
    expect(tooltip.textContent).not.toContain('\u2192');
  });

  it('renders no markers or tooltip when annotations are empty', () => {
    render(<FacsimilePage facsimile={makeFacsimile(0)} pageTitle="Test" pageNumber={1} />);
    expect(screen.queryAllByRole('button', { name: /^Annotation \d+:/ })).toHaveLength(0);
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  // S5U-697: stacking-rank defence against residual hotspot occlusion.
  // Even if the pipeline-side occlusion filter misses a near-miss pair, the
  // reader must never let a larger bbox paint on top of a smaller one — the
  // smaller marker is always the more-specific hotspot.
  it('assigns higher z-index to smaller-bbox annotations', () => {
    const facsimile: RenderFacsimile = {
      raster_src: '/test.png',
      width_px: 800,
      height_px: 1200,
      annotations: [
        // Large bbox (area 0.04): should paint beneath the small one.
        {
          text: 'Large enclosing region',
          translated_text: 'Большой регион',
          bbox: { x0: 0.2, y0: 0.2, x1: 0.4, y1: 0.4 },
          kind: 'body',
          priority: 0,
        },
        // Small bbox (area 0.0025): must paint on top.
        {
          text: 'Small inner hotspot',
          translated_text: 'Малый',
          bbox: { x0: 0.28, y0: 0.28, x1: 0.33, y1: 0.33 },
          kind: 'body',
          priority: 0,
        },
      ],
    };
    render(<FacsimilePage facsimile={facsimile} pageTitle="Test" pageNumber={1} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    const smallMarker = markers.find((m) => m.getAttribute('aria-label')?.includes('Малый'));
    const largeMarker = markers.find((m) =>
      m.getAttribute('aria-label')?.includes('Большой регион'),
    );
    expect(smallMarker).toBeTruthy();
    expect(largeMarker).toBeTruthy();
    // Inline style uses numeric z-index; read as string and parse.
    const smallZ = Number(smallMarker!.style.zIndex);
    const largeZ = Number(largeMarker!.style.zIndex);
    expect(Number.isFinite(smallZ)).toBe(true);
    expect(Number.isFinite(largeZ)).toBe(true);
    expect(smallZ).toBeGreaterThan(largeZ);
  });

  it('promotes the active marker above every other marker', () => {
    const facsimile: RenderFacsimile = {
      raster_src: '/test.png',
      width_px: 800,
      height_px: 1200,
      annotations: [
        // Small bbox at top (rank 1).
        {
          text: 'Small',
          translated_text: 'Малый',
          bbox: { x0: 0.1, y0: 0.1, x1: 0.15, y1: 0.15 },
          kind: 'body',
          priority: 0,
        },
        // Large bbox at bottom (rank 0).
        {
          text: 'Large',
          translated_text: 'Большой',
          bbox: { x0: 0.1, y0: 0.5, x1: 0.5, y1: 0.9 },
          kind: 'body',
          priority: 0,
        },
      ],
    };
    render(<FacsimilePage facsimile={facsimile} pageTitle="Test" pageNumber={1} />);
    const markers = screen.getAllByRole('button', { name: /^Annotation \d+:/ });
    const largeMarker = markers.find((m) => m.getAttribute('aria-label')?.includes('Большой'))!;
    const smallMarker = markers.find((m) => m.getAttribute('aria-label')?.includes('Малый'))!;
    // Before activation: small > large.
    expect(Number(smallMarker.style.zIndex)).toBeGreaterThan(Number(largeMarker.style.zIndex));
    // Activate the larger one; it should jump above every other rank.
    fireEvent.click(largeMarker);
    expect(Number(largeMarker.style.zIndex)).toBeGreaterThan(Number(smallMarker.style.zIndex));
  });
});
