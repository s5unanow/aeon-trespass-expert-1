/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
/**
 * @minItems 1
 */
export type Images = [ImageSetImageEntryV1, ...ImageSetImageEntryV1[]];
export type ImageId = string;
export type Path = string;
export type MediaType = 'image/png' | 'image/jpeg';
export type Sha256 = string;
export type PageId = string;
export type PageNumber = number;
export type CapturedAt = string | null;
export type CameraMake = string | null;
export type CameraModel = string | null;
export type ExifOrientation = number | null;

/**
 * Ordered image-set source declaration.
 */
export interface ImageSetManifestV1 {
  schema_version?: SchemaVersion;
  images: Images;
}
/**
 * One ordered image in an image-set input manifest.
 */
export interface ImageSetImageEntryV1 {
  image_id: ImageId;
  path: Path;
  media_type: MediaType;
  sha256: Sha256;
  page_id: PageId;
  page_number: PageNumber;
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
