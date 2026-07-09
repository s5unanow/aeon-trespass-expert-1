import { useCallback, useMemo, useState } from 'react';
import type { RenderFacsimile } from '../../lib/render/types';
import { facsimileStackRanks, sortFacsimileAnnotations } from '../../lib/render/facsimileOverlay';

interface ReviewFacsimileProps {
  facsimile: RenderFacsimile;
  pageTitle: string;
  pageNumber: number;
  activeBlockRef: string | null;
  selectedBlockRef: string | null;
  onHover: (blockRef: string | null) => void;
  onSelect: (blockRef: string) => void;
}

export function ReviewFacsimile({
  facsimile,
  pageTitle,
  pageNumber,
  activeBlockRef,
  selectedBlockRef,
  onHover,
  onSelect,
}: ReviewFacsimileProps) {
  const [rasterLoaded, setRasterLoaded] = useState(false);
  const handleLoad = useCallback(() => setRasterLoaded(true), []);
  const annotations = useMemo(
    () =>
      sortFacsimileAnnotations(facsimile.annotations ?? []).filter(
        (annotation) => annotation.block_ref,
      ),
    [facsimile.annotations],
  );
  const stackRanks = useMemo(() => facsimileStackRanks(annotations), [annotations]);

  return (
    <div className="review-facsimile-viewport">
      <img
        src={facsimile.raster_src}
        srcSet={facsimile.raster_src_hires ? `${facsimile.raster_src_hires} 2x` : undefined}
        alt={`Page ${pageNumber}: ${pageTitle}`}
        width={facsimile.width_px || undefined}
        height={facsimile.height_px || undefined}
        className={`review-facsimile-raster img-lazy${rasterLoaded ? ' is-loaded' : ''}`}
        onLoad={handleLoad}
      />
      <div className="review-facsimile-overlay">
        {annotations.map((annotation, index) => {
          const blockRef = annotation.block_ref || '';
          const isSelected = selectedBlockRef === blockRef;
          const isActive = isSelected || activeBlockRef === blockRef;
          const { bbox } = annotation;
          return (
            <button
              key={`${blockRef}-${index}`}
              type="button"
              aria-label={`Select ${blockRef} on facsimile`}
              aria-pressed={isSelected}
              className={`review-bbox${isActive ? ' is-active' : ''}${isSelected ? ' is-selected' : ''}`}
              style={{
                left: `${bbox.x0 * 100}%`,
                top: `${bbox.y0 * 100}%`,
                width: `${(bbox.x1 - bbox.x0) * 100}%`,
                height: `${(bbox.y1 - bbox.y0) * 100}%`,
                zIndex: isSelected ? 1000 : 1 + (stackRanks[index] ?? 0),
              }}
              onMouseEnter={() => onHover(blockRef)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(blockRef)}
              onBlur={() => onHover(null)}
              onClick={() => onSelect(blockRef)}
            >
              <span>{index + 1}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
