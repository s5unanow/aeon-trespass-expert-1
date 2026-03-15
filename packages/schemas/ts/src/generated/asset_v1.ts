/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type AssetId = string;
export type AssetKind = 'figure_image' | 'inline_symbol' | 'decorative' | 'page_crop';
export type MimeType = string;
export type SourcePageId = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type Sha256 = string;
export type Phash = string;
export type CatalogBinding = string | null;
export type Variant = string;
export type Path = string;
export type MimeType1 = string;
export type WidthPx = number;
export type HeightPx = number;
export type Variants = AssetVariant[];
export type CaptionBlockId = string | null;

/**
 * An extracted or catalogued asset (figure, inline symbol, etc.).
 */
export interface AssetV1 {
  schema_version?: SchemaVersion;
  asset_id: AssetId;
  kind: AssetKind;
  mime_type?: MimeType;
  source_page_id?: SourcePageId;
  bbox?: Rect | null;
  sha256?: Sha256;
  phash?: Phash;
  pixel_size?: PixelSize;
  catalog_binding?: CatalogBinding;
  variants?: Variants;
  placement_hint?: PlacementHint;
  caption_block_id?: CaptionBlockId;
}
/**
 * Bounding box in PDF points: [x0, y0, x1, y1].
 */
export interface Rect {
  x0: X0;
  y0: Y0;
  x1: X1;
  y1: Y1;
}
export interface PixelSize {
  [k: string]: number;
}
/**
 * A size/format variant of an asset.
 */
export interface AssetVariant {
  variant: Variant;
  path?: Path;
  mime_type?: MimeType1;
  width_px?: WidthPx;
  height_px?: HeightPx;
}
export interface PlacementHint {
  [k: string]: unknown;
}
