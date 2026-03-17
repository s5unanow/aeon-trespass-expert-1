import type { RenderBlock, RenderFigure } from '../../lib/render/types';
import { HeadingBlock } from './HeadingBlock';
import { ParagraphBlock } from './ParagraphBlock';
import { FigureBlock } from './FigureBlock';
import { ListItemBlock } from './ListItemBlock';

interface BlockRendererProps {
  block: RenderBlock;
  figures?: Record<string, RenderFigure>;
}

export function BlockRenderer({ block, figures }: BlockRendererProps) {
  switch (block.kind) {
    case 'heading':
      return <HeadingBlock block={block} />;
    case 'paragraph':
      return <ParagraphBlock block={block} />;
    case 'figure':
      return <FigureBlock block={block} figures={figures} />;
    case 'list_item':
      return <ListItemBlock block={block} />;
    case 'divider':
      return <hr id={block.id} className="reader-divider" />;
    default:
      return null;
  }
}
