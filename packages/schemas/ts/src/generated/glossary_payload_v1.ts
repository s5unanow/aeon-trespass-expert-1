/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type ConceptId = string;
export type PreferredTerm = string;
export type SourceTerm = string;
export type Aliases = string[];
export type IconBinding = string | null;
export type Notes = string;
export type PageId = string;
export type SourcePageNumber = number;
export type PageRefs = GlossaryPageRef[];
export type Entries = GlossaryEntryV1[];

/**
 * Frontend glossary payload.
 */
export interface GlossaryPayloadV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  entries?: Entries;
}
/**
 * A single glossary entry for the frontend.
 */
export interface GlossaryEntryV1 {
  concept_id: ConceptId;
  preferred_term: PreferredTerm;
  source_term?: SourceTerm;
  aliases?: Aliases;
  icon_binding?: IconBinding;
  notes?: Notes;
  page_refs?: PageRefs;
}
/**
 * A page where a glossary concept is mentioned.
 */
export interface GlossaryPageRef {
  page_id: PageId;
  source_page_number: SourcePageNumber;
}
