import type { RenderCaptionBlock as CaptionData } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface CaptionBlockProps {
  block: CaptionData;
}

/**
 * S5U-737 — render an orphan ``RenderCaptionBlock``.
 *
 * Captions whose ``figure_block_id`` resolves to a figure on the same page
 * are folded into ``RenderFigure.caption`` upstream and never reach this
 * component; only orphan captions arrive here. The ``data-orphan="true"``
 * attribute marks the block visually so the prose can be styled distinctly
 * from a regular paragraph and so QA tools (and visual review) can spot
 * orphaned captions on the page.
 */
export function CaptionBlock({ block }: CaptionBlockProps) {
  return (
    <aside id={block.id} className="reader-caption" data-orphan="true">
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </aside>
  );
}
