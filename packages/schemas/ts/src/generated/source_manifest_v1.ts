/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type SourceKind = 'pdf' | 'image_set';
export type SourcePdfSha256 = string;
export type SourceImageSetSha256 = string;
export type SourceImageSetManifestSha256 = string;
export type PageCount = number;
export type PageId = string;
export type PageNumber = number;
export type RasterRef = string | null;
export type SourceImageId = string | null;
export type RawImageRef = string | null;
export type Pages = PageEntry[];
export type SchemaVersion1 = string;
export type SourceKind1 = 'image_set';
/**
 * @minItems 1
 */
export type Images = [ImageSetImageV1, ...ImageSetImageV1[]];
export type ImageId = string;
export type PageId1 = string;
export type PageNumber1 = number;
export type Path = string;
export type MediaType = 'image/png' | 'image/jpeg';
export type Sha256 = string;
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
  source_image_set_manifest_sha256?: SourceImageSetManifestSha256;
  page_count: PageCount;
  pages: Pages;
  image_set?: ImageSetManifestV1 | null;
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
  source_image_id?: SourceImageId;
  raw_image_ref?: RawImageRef;
}
/**
 * Authoritative ordered mapping from source pages to raw image files.
 */
export interface ImageSetManifestV1 {
  schema_version?: SchemaVersion1;
  source_kind?: SourceKind1;
  images: Images;
}
/**
 * Metadata for one raw source image.
 */
export interface ImageSetImageV1 {
  image_id: ImageId;
  page_id: PageId1;
  page_number: PageNumber1;
  path: Path;
  media_type: MediaType;
  sha256: Sha256;
  capture?: Capture;
  exif?: Exif;
}
export interface Capture {
  [k: string]: string | number | number | boolean | null;
}
export interface Exif {
  [k: string]: string | number | number | boolean | null;
}
