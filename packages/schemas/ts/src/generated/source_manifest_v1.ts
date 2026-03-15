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

/**
 * Registered source document and its pages.
 */
export interface SourceManifestV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  source_pdf_sha256: SourcePdfSha256;
  page_count: PageCount;
  pages: Pages;
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
