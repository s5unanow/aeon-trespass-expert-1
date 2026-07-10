/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type SourceKind = 'pdf' | 'image_set';
export type SourcePdfSha256 = string;
export type SourceManifestSha256 = string;
export type SourceImageSetSha256 = string;
export type PageCount = number;
export type PageId = string;
export type PageNumber = number;
export type RasterRef = string | null;
export type Pages = PageEntry[];
export type ImageId = string;
export type PageId1 = string;
export type PageNumber1 = number;
export type MediaType = 'image/png' | 'image/jpeg';
export type Sha256 = string;
export type RawArtifactRef = string;
export type CapturedAt = string | null;
export type CameraMake = string | null;
export type CameraModel = string | null;
export type ExifOrientation = number | null;
export type SourceImages = SourceImageEntryV1[];
export type ConfigHash = string;
export type ExtractorVersion = string;

/**
 * Registered source document and its pages.
 */
export interface SourceManifestV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  source_kind?: SourceKind;
  source_pdf_sha256: SourcePdfSha256;
  source_manifest_sha256?: SourceManifestSha256;
  source_image_set_sha256?: SourceImageSetSha256;
  page_count: PageCount;
  pages: Pages;
  source_images?: SourceImages;
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
 * Registered immutable raw image and its source-page mapping.
 */
export interface SourceImageEntryV1 {
  image_id: ImageId;
  page_id: PageId1;
  page_number: PageNumber1;
  media_type: MediaType;
  sha256: Sha256;
  raw_artifact_ref: RawArtifactRef;
  capture?: CaptureMetadataV1;
}
/**
 * Capture and EXIF metadata retained with a photographed page.
 */
export interface CaptureMetadataV1 {
  captured_at?: CapturedAt;
  camera_make?: CameraMake;
  camera_model?: CameraModel;
  exif_orientation?: ExifOrientation;
}
