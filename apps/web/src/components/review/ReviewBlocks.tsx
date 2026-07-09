import { BlockRenderer } from '../reader/BlockRenderer';
import type { RenderBlock, RenderFigure } from '../../lib/render/types';

interface ReviewBlocksProps {
  blocks: RenderBlock[];
  figures: Record<string, RenderFigure>;
  activeBlockRef: string | null;
  selectedBlockRef: string | null;
  onHover: (blockRef: string | null) => void;
  onSelect: (blockRef: string) => void;
}

export function ReviewBlocks({
  blocks,
  figures,
  activeBlockRef,
  selectedBlockRef,
  onHover,
  onSelect,
}: ReviewBlocksProps) {
  return (
    <div className="review-rendered-blocks" aria-label="Rendered blocks">
      {blocks.map((block, index) => {
        const isSelected = selectedBlockRef === block.id;
        const isActive = isSelected || activeBlockRef === block.id;
        return (
          <div
            key={block.id}
            className={`review-block${isActive ? ' is-active' : ''}${isSelected ? ' is-selected' : ''}`}
            data-block-ref={block.id}
            onMouseEnter={() => onHover(block.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(block.id)}
            onBlur={() => onHover(null)}
            onClick={(event) => {
              if (
                event.target instanceof Element &&
                event.target.closest('a, button, input, select, textarea')
              ) {
                return;
              }
              onSelect(block.id);
            }}
          >
            <button
              type="button"
              className="review-block-index"
              aria-label={`Select ${block.id} rendered block`}
              aria-pressed={isSelected}
              onClick={() => onSelect(block.id)}
            >
              {index + 1}
            </button>
            <BlockRenderer block={block} figures={figures} />
          </div>
        );
      })}
    </div>
  );
}
