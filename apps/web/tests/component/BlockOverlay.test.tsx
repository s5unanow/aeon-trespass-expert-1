import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BlockOverlay, type OverlayItem } from '../../src/components/review/BlockOverlay';

afterEach(cleanup);

const raster = { src: '/raster.png', width: 400, height: 520, alt: 'Facsimile' };

const items: OverlayItem[] = [
  { ref: 'b1', bbox: { x0: 0, y0: 0, x1: 1, y1: 1 }, label: 'big region' }, // area 1
  { ref: 'b2', bbox: { x0: 0.1, y0: 0.1, x1: 0.2, y1: 0.2 }, label: 'small region' }, // area 0.01
];

describe('BlockOverlay', () => {
  it('renders one marker per item with a block-ref hook', () => {
    render(
      <BlockOverlay
        raster={raster}
        items={items}
        activeRef={null}
        onActivate={vi.fn()}
        onHover={vi.fn()}
      />,
    );
    const markers = screen.getAllByRole('button');
    expect(markers).toHaveLength(2);
    expect(markers[0].getAttribute('data-block-ref')).toBe('b1');
    expect(markers[1].getAttribute('data-block-ref')).toBe('b2');
  });

  it('stacks the smaller bbox above the larger one (S5U-697)', () => {
    render(
      <BlockOverlay
        raster={raster}
        items={items}
        activeRef={null}
        onActivate={vi.fn()}
        onHover={vi.fn()}
      />,
    );
    const [big, small] = screen.getAllByRole('button');
    expect(Number(small.style.zIndex)).toBeGreaterThan(Number(big.style.zIndex));
  });

  it('fires onActivate with the block ref on click', () => {
    const onActivate = vi.fn();
    render(
      <BlockOverlay
        raster={raster}
        items={items}
        activeRef={null}
        onActivate={onActivate}
        onHover={vi.fn()}
      />,
    );
    fireEvent.click(screen.getAllByRole('button')[1]);
    expect(onActivate).toHaveBeenCalledWith('b2');
  });

  it('fires onHover on mouse enter / leave', () => {
    const onHover = vi.fn();
    render(
      <BlockOverlay
        raster={raster}
        items={items}
        activeRef="b1"
        onActivate={vi.fn()}
        onHover={onHover}
      />,
    );
    const marker = screen.getAllByRole('button')[0];
    fireEvent.mouseEnter(marker);
    expect(onHover).toHaveBeenCalledWith('b1');
    fireEvent.mouseLeave(marker);
    expect(onHover).toHaveBeenCalledWith(null);
  });

  it('marks the active ref with aria-pressed', () => {
    render(
      <BlockOverlay
        raster={raster}
        items={items}
        activeRef="b2"
        onActivate={vi.fn()}
        onHover={vi.fn()}
      />,
    );
    const [big, small] = screen.getAllByRole('button');
    expect(small.getAttribute('aria-pressed')).toBe('true');
    expect(big.getAttribute('aria-pressed')).toBe('false');
  });
});
