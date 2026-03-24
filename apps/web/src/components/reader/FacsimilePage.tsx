import type { RenderFacsimile } from '../../lib/render/types';

interface FacsimilePageProps {
  facsimile: RenderFacsimile;
  pageTitle: string;
  pageNumber: number;
}

export function FacsimilePage({ facsimile, pageTitle, pageNumber }: FacsimilePageProps) {
  return (
    <div className="facsimile-page">
      <img
        src={facsimile.raster_src}
        srcSet={facsimile.raster_src_hires ? `${facsimile.raster_src_hires} 2x` : undefined}
        alt={`Page ${pageNumber}: ${pageTitle}`}
        width={facsimile.width_px || undefined}
        height={facsimile.height_px || undefined}
        className="facsimile-raster"
        loading="lazy"
      />
    </div>
  );
}
