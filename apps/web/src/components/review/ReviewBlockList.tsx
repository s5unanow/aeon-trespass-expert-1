import type { RenderBlock, RenderFigure } from '../../lib/render/types';
import { BlockRenderer } from '../reader/BlockRenderer';

interface ReviewBlockListProps {
  blocks: RenderBlock[];
  figures: Record<string, RenderFigure>;
  activeRef: string | null;
  onActivate: (ref: string) => void;
  onHover: (ref: string | null) => void;
}

/**
 * The rendered-blocks pane of the review split view. Each block is rendered by
 * the shared `BlockRenderer` and wrapped in a selectable region that stays in
 * sync (highlight + selection) with the facsimile overlay via `block.id`.
 */
export function ReviewBlockList({
  blocks,
  figures,
  activeRef,
  onActivate,
  onHover,
}: ReviewBlockListProps) {
  return (
    <ol className="review-block-list">
      {blocks.map((block, i) => {
        const isActive = block.id === activeRef;
        return (
          <li
            key={block.id}
            className={`review-block${isActive ? ' is-active' : ''}`}
            data-block-ref={block.id}
            onMouseEnter={() => onHover(block.id)}
            onMouseLeave={() => onHover(null)}
          >
            <div className="review-block-header">
              <span className="review-block-index" aria-hidden="true">
                {i + 1}
              </span>
              <span className="review-block-kind">{block.kind}</span>
              <button
                type="button"
                className="review-block-select"
                aria-pressed={isActive}
                aria-label={`Select block ${i + 1} (${block.kind}) for correction`}
                onClick={() => onActivate(block.id)}
              >
                {isActive ? 'Selected' : 'Select'}
              </button>
            </div>
            <div className="review-block-body">
              <BlockRenderer block={block} figures={figures} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
