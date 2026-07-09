/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type SourceKind = 'image_set';
/**
 * @minItems 1
 */
export type Images = [ImageSetImageV1, ...ImageSetImageV1[]];
export type ImageId = string;
export type PageId = string;
export type PageNumber = number;
export type Path = string;
export type MediaType = 'image/png' | 'image/jpeg';
export type Sha256 = string;

/**
 * Authoritative ordered mapping from source pages to raw image files.
 */
export interface ImageSetManifestV1 {
  schema_version?: SchemaVersion;
  source_kind?: SourceKind;
  images: Images;
}
/**
 * Metadata for one raw source image.
 */
export interface ImageSetImageV1 {
  image_id: ImageId;
  page_id: PageId;
  page_number: PageNumber;
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
