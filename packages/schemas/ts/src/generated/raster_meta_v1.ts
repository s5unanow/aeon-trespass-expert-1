/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
export type SourcePdfSha256 = string;
export type RenderEngine = string;
export type RenderEngineVersion = string;
export type Dpi = number;
export type WidthPx = number;
export type HeightPx = number;
export type ContentHash = string;
/**
 * Path relative to artifact root
 */
export type RelativePath = string;
export type Levels = RasterLevel[];

/**
 * Provenance metadata for all rendered raster levels of a page.
 */
export interface RasterMetaV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  source_pdf_sha256: SourcePdfSha256;
  render_engine?: RenderEngine;
  render_engine_version?: RenderEngineVersion;
  levels?: Levels;
}
/**
 * Metadata for a single raster resolution level.
 */
export interface RasterLevel {
  dpi: Dpi;
  width_px: WidthPx;
  height_px: HeightPx;
  content_hash: ContentHash;
  relative_path: RelativePath;
}
