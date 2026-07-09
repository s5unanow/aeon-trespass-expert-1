import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { FacsimileAnnotation, RenderFacsimile } from '../../lib/render/types';
import { assignStackRanks, readingOrderCompare } from '../../lib/render/overlayStacking';

interface FacsimilePageProps {
  facsimile: RenderFacsimile;
  pageTitle: string;
  pageNumber: number;
}

export function FacsimilePage({ facsimile, pageTitle, pageNumber }: FacsimilePageProps) {
  const [rasterLoaded, setRasterLoaded] = useState(false);
  const handleRasterLoad = useCallback(() => setRasterLoaded(true), []);
  const annotations = useMemo(
    () =>
      [...((facsimile.annotations ?? []) as FacsimileAnnotation[])].sort((a, b) =>
        readingOrderCompare(a.bbox, b.bbox),
      ),
    [facsimile.annotations],
  );
  // S5U-697: assign a stacking rank so smaller bboxes render above larger
  // ones — this keeps inner (more-specific) hotspots clickable even if the
  // pipeline-side occlusion filter missed a near-miss pair. Rank 0 is the
  // largest bbox; higher ranks paint later and therefore stack higher.
  const stackRanks = useMemo(() => assignStackRanks(annotations), [annotations]);
  const hasAnnotations = annotations.length > 0;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  const handleMarkerClick = useCallback((index: number) => {
    setActiveIndex((prev) => (prev === index ? null : index));
  }, []);

  useEffect(() => {
    if (activeIndex === null) return;
    function handleClickOutside(e: MouseEvent) {
      if (overlayRef.current && !overlayRef.current.contains(e.target as Node)) {
        setActiveIndex(null);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setActiveIndex(null);
    }
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [activeIndex]);

  return (
    <div className={`facsimile-page${hasAnnotations ? ' has-annotations' : ''}`}>
      <div className="facsimile-layout">
        <div className="facsimile-viewport">
          <img
            src={facsimile.raster_src}
            srcSet={facsimile.raster_src_hires ? `${facsimile.raster_src_hires} 2x` : undefined}
            alt={`Page ${pageNumber}: ${pageTitle}`}
            width={facsimile.width_px || undefined}
            height={facsimile.height_px || undefined}
            className={`facsimile-raster img-lazy${rasterLoaded ? ' is-loaded' : ''}`}
            loading="lazy"
            onLoad={handleRasterLoad}
          />
          {hasAnnotations && (
            <div className="facsimile-overlay" ref={overlayRef}>
              {annotations.map((ann, i) => (
                <AnnotationMarker
                  key={i}
                  index={i}
                  annotation={ann}
                  isActive={activeIndex === i}
                  tooltipId={activeIndex === i ? 'facsimile-tooltip' : undefined}
                  onClick={handleMarkerClick}
                  stackRank={stackRanks[i] ?? 0}
                />
              ))}
              {activeIndex !== null && <AnnotationTooltip annotation={annotations[activeIndex]} />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function AnnotationMarker({
  index,
  annotation,
  isActive,
  tooltipId,
  onClick,
  stackRank,
}: {
  index: number;
  annotation: FacsimileAnnotation;
  isActive: boolean;
  tooltipId?: string;
  onClick: (index: number) => void;
  stackRank: number;
}) {
  const { bbox } = annotation;
  const cx = ((bbox.x0 + bbox.x1) / 2) * 100;
  const cy = ((bbox.y0 + bbox.y1) / 2) * 100;
  const display = annotation.translated_text || annotation.text;
  // S5U-697: baseline 1 + stackRank keeps every marker above the raster
  // (z-index: 0) while preserving the smaller-on-top invariant. Active
  // marker jumps to the top of the overlay so its tooltip never hides
  // behind a sibling with a higher stack rank.
  const zIndex = isActive ? 1000 : 1 + stackRank;

  return (
    <button
      type="button"
      className={`facsimile-marker${isActive ? ' is-active' : ''}`}
      style={{ left: `${cx}%`, top: `${cy}%`, zIndex }}
      aria-label={`Annotation ${index + 1}: ${display}`}
      aria-describedby={tooltipId}
      onClick={() => onClick(index)}
    >
      {index + 1}
    </button>
  );
}

function AnnotationTooltip({ annotation }: { annotation: FacsimileAnnotation }) {
  const { bbox } = annotation;
  const cx = ((bbox.x0 + bbox.x1) / 2) * 100;
  const cy = ((bbox.y0 + bbox.y1) / 2) * 100;
  const hasTranslation =
    annotation.translated_text && annotation.text !== annotation.translated_text;

  return (
    <div
      className="facsimile-tooltip"
      id="facsimile-tooltip"
      role="tooltip"
      style={{ left: `${cx}%`, top: `${cy}%` }}
    >
      {hasTranslation ? (
        <>
          <span className="facsimile-tooltip-original">{annotation.text}</span>
          <span className="facsimile-tooltip-arrow">{'\u2192'}</span>
          <span className="facsimile-tooltip-translated">{annotation.translated_text}</span>
        </>
      ) : (
        <span className="facsimile-tooltip-translated">
          {annotation.translated_text || annotation.text}
        </span>
      )}
    </div>
  );
}
