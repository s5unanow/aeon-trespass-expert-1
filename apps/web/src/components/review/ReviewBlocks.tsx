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
            role="button"
            tabIndex={0}
            aria-label={`Select ${block.id} rendered block`}
            aria-pressed={isSelected}
            onMouseEnter={() => onHover(block.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(block.id)}
            onBlur={() => onHover(null)}
            onClick={() => onSelect(block.id)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelect(block.id);
              }
            }}
          >
            <span className="review-block-index">{index + 1}</span>
            <BlockRenderer block={block} figures={figures} />
          </div>
        );
      })}
    </div>
  );
}
