/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type SourceKind = 'pdf' | 'image_set';
export type SourcePdfSha256 = string;
export type SourceImageSetSha256 = string;
export type PageCount = number;
export type PageId = string;
export type PageNumber = number;
export type RasterRef = string | null;
export type Pages = PageEntry[];
export type ImageId = string;
export type Sha256 = string;
export type PageNumber1 = number;
export type MediaType = string;
/**
 * File extension including the leading dot.
 */
export type Extension = string;
export type WidthPx = number | null;
export type HeightPx = number | null;
export type ArtifactRef = string;
export type Images = SourceImageRef[];
export type ConfigHash = string;
export type ExtractorVersion = string;

/**
 * Registered source document and its pages.
 */
export interface SourceManifestV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  source_kind?: SourceKind;
  source_pdf_sha256?: SourcePdfSha256;
  source_image_set_sha256?: SourceImageSetSha256;
  page_count: PageCount;
  pages: Pages;
  images?: Images;
  config_hash?: ConfigHash;
  extractor_version?: ExtractorVersion;
}
/**
 * Metadata for a single source page.
 */
export interface PageEntry {
  page_id: PageId;
  page_number: PageNumber;
  raster_ref?: RasterRef;
}
/**
 * A raw source image registered by image-set ingest.
 *
 * ``sha256`` is the hex digest of the raw file bytes as stored (the artifact
 * is content-addressed by the same digest). ``artifact_ref`` is the relative
 * path within the artifact store.
 */
export interface SourceImageRef {
  image_id: ImageId;
  sha256: Sha256;
  page_number: PageNumber1;
  media_type: MediaType;
  extension: Extension;
  width_px?: WidthPx;
  height_px?: HeightPx;
  artifact_ref?: ArtifactRef;
}
