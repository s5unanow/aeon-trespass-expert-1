/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type CatalogId = string;
export type Version = string;
export type SymbolId = string;
export type Label = string;
export type AltLabelRu = string;
export type TemplateAsset = string;
export type MatchThreshold = number;
export type Inline = boolean;
export type Symbols = SymbolEntry[];

/**
 * Catalog of known symbols for matching.
 */
export interface SymbolCatalogV1 {
  schema_version?: SchemaVersion;
  catalog_id?: CatalogId;
  version?: Version;
  symbols?: Symbols;
}
/**
 * A single symbol definition in the catalog.
 */
export interface SymbolEntry {
  symbol_id: SymbolId;
  label: Label;
  alt_label_ru?: AltLabelRu;
  template_asset?: TemplateAsset;
  match_threshold?: MatchThreshold;
  inline?: Inline;
}
