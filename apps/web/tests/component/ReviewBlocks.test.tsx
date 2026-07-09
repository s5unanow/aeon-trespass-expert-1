import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { ReviewBlocks } from '../../src/components/review/ReviewBlocks';
import type { RenderBlock } from '../../src/lib/render/types';

const blocks: RenderBlock[] = [
  {
    kind: 'paragraph',
    id: 'p0001.b001',
    children: [
      {
        kind: 'figure_ref',
        asset_id: 'fig.example',
        label: 'Figure 1',
      },
    ],
  },
];

describe('ReviewBlocks', () => {
  it('keeps descendant links independent from block selection', () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <ReviewBlocks
          blocks={blocks}
          figures={{}}
          activeBlockRef={null}
          selectedBlockRef={null}
          onHover={vi.fn()}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: 'Figure 1' });
    expect(fireEvent.keyDown(link, { key: 'Enter' })).toBe(true);
    expect(onSelect).not.toHaveBeenCalled();

    const selectButton = screen.getByRole('button', { name: /Select p0001\.b001/ });
    expect(selectButton.contains(link)).toBe(false);
    fireEvent.click(link);
    expect(onSelect).not.toHaveBeenCalled();

    fireEvent.click(selectButton);
    expect(onSelect).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith('p0001.b001');
  });
});
