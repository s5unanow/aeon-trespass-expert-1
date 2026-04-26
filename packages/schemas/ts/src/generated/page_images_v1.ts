/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type PageNumber = number;
/**
 * Namespaced image id of the form ``p{page_number:04d}.img{idx:04d}`` matching the entity_id used by the ``image`` artifact family.
 */
export type ImageId = string;
/**
 * Decoded image width in pixels.
 */
export type WidthPx = number;
/**
 * Decoded image height in pixels.
 */
export type HeightPx = number;
/**
 * File extension including leading dot (e.g. ``.png``, ``.jpeg``).
 */
export type Extension = string;
export type Images = PageImageEntry[];

/**
 * Per-page manifest of source-PDF images, scoped to ``page``.
 */
export interface PageImagesV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  page_number: PageNumber;
  images?: Images;
}
/**
 * One image extracted from the source PDF for a given page.
 */
export interface PageImageEntry {
  image_id: ImageId;
  width_px: WidthPx;
  height_px: HeightPx;
  extension: Extension;
}
