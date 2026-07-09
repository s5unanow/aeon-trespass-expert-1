import { useMemo } from 'react';
import { assignStackRanks, type Bbox } from '../../lib/render/overlayStacking';

/** One positioned marker over the facsimile raster, tied to a block ref. */
export interface OverlayItem {
  /** `block.id` this marker represents — the sync key with the block list. */
  ref: string;
  bbox: Bbox;
  /** Short label shown inside / around the marker. */
  label: string;
}

interface BlockOverlayProps {
  raster: {
    src: string;
    srcHires?: string;
    width?: number;
    height?: number;
    alt: string;
  };
  items: OverlayItem[];
  activeRef: string | null;
  onActivate: (ref: string) => void;
  onHover: (ref: string | null) => void;
}

/**
 * Facsimile raster + per-block bbox markers. Reuses the S5U-697 stacking rule
 * (`assignStackRanks`) so a smaller, more-specific box always stays clickable
 * above a larger enclosing one. Each marker carries its `ref` so hover/click
 * sync with the block list survives the area-based stacking sort.
 */
export function BlockOverlay({ raster, items, activeRef, onActivate, onHover }: BlockOverlayProps) {
  const stackRanks = useMemo(() => assignStackRanks(items), [items]);

  return (
    <div className="review-facsimile-viewport">
      <img
        src={raster.src}
        srcSet={raster.srcHires ? `${raster.srcHires} 2x` : undefined}
        alt={raster.alt}
        width={raster.width || undefined}
        height={raster.height || undefined}
        className="review-facsimile-raster"
        loading="lazy"
      />
      <div className="review-facsimile-overlay">
        {items.map((item, i) => {
          const cx = ((item.bbox.x0 + item.bbox.x1) / 2) * 100;
          const cy = ((item.bbox.y0 + item.bbox.y1) / 2) * 100;
          const isActive = item.ref === activeRef;
          // 1 + rank keeps every marker above the raster; the active marker
          // jumps to the top so it always owns its click target (S5U-697).
          const zIndex = isActive ? 1000 : 1 + (stackRanks[i] ?? 0);
          return (
            <button
              key={item.ref}
              type="button"
              className={`review-overlay-marker${isActive ? ' is-active' : ''}`}
              style={{ left: `${cx}%`, top: `${cy}%`, zIndex }}
              data-block-ref={item.ref}
              aria-label={`Block ${i + 1}: ${item.label}`}
              aria-pressed={isActive}
              onClick={() => onActivate(item.ref)}
              onMouseEnter={() => onHover(item.ref)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(item.ref)}
              onBlur={() => onHover(null)}
            >
              {i + 1}
            </button>
          );
        })}
      </div>
    </div>
  );
}
