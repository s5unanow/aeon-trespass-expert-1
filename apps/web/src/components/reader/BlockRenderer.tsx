import type { RenderBlock, RenderFigure } from '../../lib/render/types';
import { CalloutBlock } from './CalloutBlock';
import { FigureBlock } from './FigureBlock';
import { HeadingBlock } from './HeadingBlock';
import { ListItemBlock } from './ListItemBlock';
import { ParagraphBlock } from './ParagraphBlock';
import { TableBlock } from './TableBlock';

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
    case 'callout':
      return <CalloutBlock block={block} />;
    case 'table':
      return <TableBlock block={block} />;
    case 'divider':
      return <hr id={block.id} className="reader-divider" />;
    default: {
      const _exhaustive: never = block;
      console.error('Unsupported block kind:', (_exhaustive as RenderBlock).kind);
      return (
        <div className="reader-unsupported-block" data-kind={(_exhaustive as RenderBlock).kind}>
          [Unsupported block]
        </div>
      );
    }
  }
}
