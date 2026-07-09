import { useMemo } from 'react';
import type { RenderBlock } from '../../lib/render/types';

interface Region {
  index: number;
  top: number;
  left: number;
  width: number;
  height: number;
  label: string;
}

interface Props {
  blocks: RenderBlock[];
  selectedIndex: number | null;
  hoverIndex: number | null;
  hasFacsimile: boolean;
  onRegionClick: (idx: number) => void;
  onHover: (idx: number | null) => void;
}

function getBlockLabel(block: RenderBlock, idx: number): string {
  const anyB = block as any;
  const kind = anyB.kind || 'block';
  const ch = Array.isArray(anyB.children) ? anyB.children : [];
  const t = ch.find((c: any) => c && c.kind === 'text');
  const preview = t ? (t.text || '').slice(0, 48) : '';
  return `${kind}#${idx}${preview ? ` — ${preview}` : ''}`;
}

export function ReviewFacsimileOverlay({
  blocks,
  selectedIndex,
  hoverIndex,
  hasFacsimile,
  onRegionClick,
  onHover,
}: Props) {
  const blockCount = blocks.length;
  const regions: Region[] = useMemo(() => {
    return blocks.map((b, i) => {
      const top = (i / Math.max(1, blockCount)) * 88 + 4;
      const height = Math.max(6, 92 / Math.max(1, blockCount));
      const left = 8 + (i % 3) * 4;
      const width = 78;
      return { index: i, top, left, width, height, label: getBlockLabel(b, i) };
    });
  }, [blocks, blockCount]);

  return (
    <div className="review-facsimile-viewport" aria-label="Facsimile raster area with selectable block regions">
      {/* When real facsimile present the parent passes an <img> sibling; placeholder provides the overlay surface */}
      <div
        className="review-facsimile-placeholder"
        style={hasFacsimile ? { position: 'absolute', inset: 0, background: 'transparent' } : undefined}
      >
        {!hasFacsimile && 'Facsimile raster not present in this fixture (overlays still interactive)'}
        {regions.map((r) => (
          <div
            key={r.index}
            role="button"
            tabIndex={0}
            className={`review-block-region${selectedIndex === r.index ? ' is-selected' : ''}${hoverIndex === r.index ? ' is-hovered' : ''}`}
            style={{
              top: `${r.top}%`,
              left: `${r.left}%`,
              width: `${r.width}%`,
              height: `${r.height}%`,
              zIndex: selectedIndex === r.index ? 100 : 1 + (regions.length - r.index),
            }}
            aria-label={`Select block ${r.index}`}
            onClick={() => onRegionClick(r.index)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onRegionClick(r.index);
              }
            }}
            onMouseEnter={() => onHover(r.index)}
            onMouseLeave={() => onHover(null)}
          >
            {r.index}
          </div>
        ))}
      </div>
    </div>
  );
}
