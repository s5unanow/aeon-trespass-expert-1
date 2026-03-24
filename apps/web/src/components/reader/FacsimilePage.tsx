import { useState } from 'react';
import type { FacsimileAnnotation, RenderFacsimile } from '../../lib/render/types';

interface FacsimilePageProps {
  facsimile: RenderFacsimile;
  pageTitle: string;
  pageNumber: number;
}

export function FacsimilePage({ facsimile, pageTitle, pageNumber }: FacsimilePageProps) {
  const annotations = (facsimile.annotations ?? []) as FacsimileAnnotation[];
  const hasAnnotations = annotations.length > 0;

  return (
    <div className="facsimile-page">
      <div className="facsimile-viewport">
        <img
          src={facsimile.raster_src}
          srcSet={facsimile.raster_src_hires ? `${facsimile.raster_src_hires} 2x` : undefined}
          alt={`Page ${pageNumber}: ${pageTitle}`}
          width={facsimile.width_px || undefined}
          height={facsimile.height_px || undefined}
          className="facsimile-raster"
          loading="lazy"
        />
        {hasAnnotations && (
          <div className="facsimile-overlay" aria-hidden="true">
            {annotations.map((ann, i) => (
              <AnnotationHotspot key={i} annotation={ann} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AnnotationHotspot({ annotation }: { annotation: FacsimileAnnotation }) {
  const [expanded, setExpanded] = useState(false);
  const { bbox } = annotation;
  const display = annotation.translated_text || annotation.text;

  const style: React.CSSProperties = {
    left: `${bbox.x0 * 100}%`,
    top: `${bbox.y0 * 100}%`,
    width: `${(bbox.x1 - bbox.x0) * 100}%`,
    height: `${(bbox.y1 - bbox.y0) * 100}%`,
  };

  return (
    <button
      type="button"
      className={`facsimile-hotspot${expanded ? ' is-expanded' : ''}`}
      style={style}
      data-kind={annotation.kind}
      onClick={() => setExpanded((v) => !v)}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      {expanded && (
        <span className="facsimile-hotspot-text">
          {display}
          {annotation.translated_text && annotation.text !== annotation.translated_text && (
            <span className="facsimile-hotspot-original">{annotation.text}</span>
          )}
        </span>
      )}
    </button>
  );
}
