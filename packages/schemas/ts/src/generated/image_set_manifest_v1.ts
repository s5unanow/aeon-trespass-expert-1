/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type PageId = string;
export type Path = string;
export type Sha256 = string | null;
export type Width = number | null;
export type Height = number | null;
export type MediaType = string | null;
export type Images = ImageEntryV1[];

/**
 * On-disk manifest describing the ordered images for an image-set source.
 *
 * This is the input artifact referenced by an ImageSetSourceV1.
 * It is validated for duplicates, path safety (by ingest), and media types
 * before any raw image bytes are registered as artifacts.
 */
export interface ImageSetManifestV1 {
  schema_version?: SchemaVersion;
  images: Images;
}
/**
 * Descriptor for one page image within an image-set source.
 *
 * - page_id uses the canonical pNNNN form for stable page identity.
 * - sha256 is the hex digest of the raw image file bytes (filled by ingest).
 * - path is relative to the manifest or repo root (resolved safely at ingest).
 */
export interface ImageEntryV1 {
  page_id: PageId;
  path: Path;
  sha256?: Sha256;
  width?: Width;
  height?: Height;
  media_type?: MediaType;
}
