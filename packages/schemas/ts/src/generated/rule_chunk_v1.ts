/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type RuleChunkId = string;
export type DocumentId = string;
export type Edition = string;
export type PageId = string;
export type SourcePageNumber = number;
export type SectionPath = string[];
export type BlockIds = string[];
export type CanonicalAnchorId = string;
export type LanguageCode = 'en' | 'ru';
export type Text = string;
export type NormalizedText = string;
export type ConceptId = string;
export type SurfaceForm = string;
export type GlossaryConcepts = GlossaryConcept[];
export type SymbolIds = string[];
export type DeepLink = string;
export type X0 = number;
export type Y0 = number;
export type X1 = number;
export type Y1 = number;
export type FacsimileBboxRefs = NormRect[];

/**
 * Semantic rule chunk anchored to canonical IR for assistant retrieval.
 *
 * Each chunk represents one answerable unit of rule text derived from
 * PageIRV1 blocks, with bilingual text payloads tied to the same
 * canonical anchor.
 */
export interface RuleChunkV1 {
  schema_version?: SchemaVersion;
  rule_chunk_id: RuleChunkId;
  document_id: DocumentId;
  edition: Edition;
  page_id: PageId;
  source_page_number: SourcePageNumber;
  section_path?: SectionPath;
  block_ids?: BlockIds;
  canonical_anchor_id: CanonicalAnchorId;
  language: LanguageCode;
  text: Text;
  normalized_text?: NormalizedText;
  glossary_concepts?: GlossaryConcepts;
  symbol_ids?: SymbolIds;
  deep_link?: DeepLink;
  facsimile_bbox_refs?: FacsimileBboxRefs;
}
/**
 * A glossary concept referenced within a rule chunk.
 */
export interface GlossaryConcept {
  concept_id: ConceptId;
  surface_form?: SurfaceForm;
}
/**
 * Bounding box in normalized [0,1] page coordinate space.
 */
export interface NormRect {
  x0: X0;
  y0: Y0;
  x1: X1;
  y1: Y1;
}
