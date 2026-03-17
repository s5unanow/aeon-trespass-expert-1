import type { RenderFigureBlock as FigureData, RenderFigure } from '../../lib/render/types';
import { InlineRenderer } from './InlineRenderer';

interface FigureBlockProps {
  block: FigureData;
  figures?: Record<string, RenderFigure>;
}

export function FigureBlock({ block, figures }: FigureBlockProps) {
  const figure = block.asset_id && figures ? figures[block.asset_id] : undefined;
  return (
    <figure id={block.id} className="reader-figure">
      {figure && (
        <img
          src={figure.src}
          alt={figure.alt || block.asset_id || 'Figure'}
          className="reader-figure-img"
          loading="lazy"
        />
      )}
      {figure?.caption && (
        <figcaption className="reader-figure-caption">{figure.caption}</figcaption>
      )}
      {block.children.map((child, i) => (
        <InlineRenderer key={i} node={child} />
      ))}
    </figure>
  );
}
