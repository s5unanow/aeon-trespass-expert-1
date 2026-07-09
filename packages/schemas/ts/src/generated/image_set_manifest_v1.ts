/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
/**
 * @minItems 1
 */
export type Images = [ImageSetImageEntry, ...ImageSetImageEntry[]];
/**
 * Stable, author-supplied identifier for this image. Must be unique within the manifest; ingest refuses duplicates. Used verbatim as the artifact entity id, so it is restricted to a filesystem-safe charset.
 */
export type ImageId = string;
/**
 * Relative path to the image file, resolved against the manifest's own directory. Must stay under the repository root after realpath resolution — ingest refuses traversal, absolute escapes, and symlink escapes.
 */
export type Path = string;
/**
 * 1-based page this image belongs to.
 */
export type PageNumber = number;
/**
 * Optional IANA media type hint (e.g. ``image/png``). When empty, ingest derives it from the decoded image format.
 */
export type MediaType = string;
export type CameraMake = string;
export type CameraModel = string;
export type CapturedAt = string;
export type Orientation = number | null;

/**
 * Ordered manifest of source images for an ``image_set`` document.
 */
export interface ImageSetManifestV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  images: Images;
}
/**
 * One source image in the ordered image set.
 */
export interface ImageSetImageEntry {
  image_id: ImageId;
  path: Path;
  page_number: PageNumber;
  media_type?: MediaType;
  capture?: CaptureMetadata | null;
}
/**
 * Optional EXIF/capture metadata for a single photographed image.
 *
 * Every field is optional — a synthetic or metadata-stripped image simply
 * omits them. ``exif`` is a free-form bag for tags not modelled explicitly so
 * a capture pipeline can preserve provenance without a schema change.
 */
export interface CaptureMetadata {
  camera_make?: CameraMake;
  camera_model?: CameraModel;
  captured_at?: CapturedAt;
  orientation?: Orientation;
  exif?: Exif;
}
export interface Exif {
  [k: string]: string;
}
