/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type SourcePdfSha256 = string;
export type PageCount = number;
export type PageId = string;
export type PageNumber = number;
export type RasterRef = string | null;
export type Pages = PageEntry[];
export type ConfigHash = string;
export type ExtractorVersion = string;
export type SourceImageSetSha256 = string;
export type PageId1 = string;
export type Path = string;
export type Sha256 = string | null;
export type Width = number | null;
export type Height = number | null;
export type MediaType = string | null;
export type ImageEntries = ImageEntryV1[];

/**
 * Registered source document and its pages.
 *
 * PDF sources populate source_pdf_sha256 (historical field).
 * Image-set sources populate the complement source_image_set_sha256 and
 * may list per-image details in image_entries. The two fingerprint fields
 * coexist; neither overloads the other.
 */
export interface SourceManifestV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  source_pdf_sha256?: SourcePdfSha256;
  page_count: PageCount;
  pages: Pages;
  config_hash?: ConfigHash;
  extractor_version?: ExtractorVersion;
  source_image_set_sha256?: SourceImageSetSha256;
  image_entries?: ImageEntries;
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
 * Descriptor for one page image within an image-set source.
 *
 * - page_id uses the canonical pNNNN form for stable page identity.
 * - sha256 is the hex digest of the raw image file bytes (filled by ingest).
 * - path is relative to the manifest or repo root (resolved safely at ingest).
 */
export interface ImageEntryV1 {
  page_id: PageId1;
  path: Path;
  sha256?: Sha256;
  width?: Width;
  height?: Height;
  media_type?: MediaType;
}
