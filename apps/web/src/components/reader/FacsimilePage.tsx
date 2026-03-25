import { useCallback, useMemo, useRef, useState } from 'react';
import type { FacsimileAnnotation, RenderFacsimile } from '../../lib/render/types';

interface FacsimilePageProps {
  facsimile: RenderFacsimile;
  pageTitle: string;
  pageNumber: number;
}

/** Vertical tolerance (fraction of page height) for same-row grouping. */
const ROW_TOLERANCE = 0.02;

/** Sort annotations in reading order: top-to-bottom, then left-to-right. */
function readingOrder(a: FacsimileAnnotation, b: FacsimileAnnotation): number {
  const ay = (a.bbox.y0 + a.bbox.y1) / 2;
  const by = (b.bbox.y0 + b.bbox.y1) / 2;
  if (Math.abs(ay - by) > ROW_TOLERANCE) return ay - by;
  return a.bbox.x0 - b.bbox.x0;
}

export function FacsimilePage({ facsimile, pageTitle, pageNumber }: FacsimilePageProps) {
  const [rasterLoaded, setRasterLoaded] = useState(false);
  const handleRasterLoad = useCallback(() => setRasterLoaded(true), []);
  const annotations = useMemo(
    () => [...((facsimile.annotations ?? []) as FacsimileAnnotation[])].sort(readingOrder),
    [facsimile.annotations],
  );
  const hasAnnotations = annotations.length > 0;
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const panelRef = useRef<HTMLUListElement>(null);

  const handleMarkerClick = useCallback((index: number) => {
    setActiveIndex((prev) => {
      const next = prev === index ? null : index;
      if (next !== null) setPanelOpen(true);
      return next;
    });
    requestAnimationFrame(() => {
      const entry = panelRef.current?.querySelector(`[data-index="${index}"]`);
      entry?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  }, []);

  const handlePanelClick = useCallback((index: number) => {
    setActiveIndex((prev) => (prev === index ? null : index));
  }, []);

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
            <div className="facsimile-overlay">
              {annotations.map((ann, i) => (
                <AnnotationMarker
                  key={i}
                  index={i}
                  annotation={ann}
                  isActive={activeIndex === i}
                  onClick={handleMarkerClick}
                />
              ))}
            </div>
          )}
        </div>
        {hasAnnotations && (
          <>
            <button
              type="button"
              className="facsimile-panel-toggle"
              onClick={() => setPanelOpen((v) => !v)}
              aria-expanded={panelOpen}
            >
              {panelOpen ? 'Hide' : 'Show'} annotations ({annotations.length})
            </button>
            <ul
              className={`facsimile-panel${panelOpen ? ' is-open' : ''}`}
              ref={panelRef}
              aria-label="Annotations"
            >
              {annotations.map((ann, i) => (
                <AnnotationPanelEntry
                  key={i}
                  index={i}
                  annotation={ann}
                  isActive={activeIndex === i}
                  onClick={handlePanelClick}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

function AnnotationMarker({
  index,
  annotation,
  isActive,
  onClick,
}: {
  index: number;
  annotation: FacsimileAnnotation;
  isActive: boolean;
  onClick: (index: number) => void;
}) {
  const { bbox } = annotation;
  const cx = ((bbox.x0 + bbox.x1) / 2) * 100;
  const cy = ((bbox.y0 + bbox.y1) / 2) * 100;
  const display = annotation.translated_text || annotation.text;

  return (
    <button
      type="button"
      className={`facsimile-marker${isActive ? ' is-active' : ''}`}
      style={{ left: `${cx}%`, top: `${cy}%` }}
      aria-label={`Annotation ${index + 1}: ${display}`}
      onClick={() => onClick(index)}
    >
      {index + 1}
    </button>
  );
}

function AnnotationPanelEntry({
  index,
  annotation,
  isActive,
  onClick,
}: {
  index: number;
  annotation: FacsimileAnnotation;
  isActive: boolean;
  onClick: (index: number) => void;
}) {
  const hasTranslation =
    annotation.translated_text && annotation.text !== annotation.translated_text;

  return (
    <li data-index={index}>
      <button
        type="button"
        className={`facsimile-panel-entry${isActive ? ' is-active' : ''}`}
        onClick={() => onClick(index)}
      >
        <span className="facsimile-panel-number">{index + 1}</span>
        <span className="facsimile-panel-text">
          {hasTranslation ? (
            <>
              <span className="facsimile-panel-original">{annotation.text}</span>
              <span className="facsimile-panel-arrow">{'\u2192'}</span>
              <span className="facsimile-panel-translated">{annotation.translated_text}</span>
            </>
          ) : (
            <span className="facsimile-panel-translated">
              {annotation.translated_text || annotation.text}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}
