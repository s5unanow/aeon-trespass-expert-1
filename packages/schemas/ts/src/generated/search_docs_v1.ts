/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type Title = string;
export type Text = string;
export type NormalizedTerms = string[];
export type SectionPath = string[];
export type SourcePageNumber = number;
export type Docs = SearchDocEntry[];

/**
 * Collection of search documents for a document edition.
 */
export interface SearchDocsV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  docs?: Docs;
}
/**
 * A single searchable document entry.
 */
export interface SearchDocEntry {
  page_id: PageId;
  title?: Title;
  text?: Text;
  normalized_terms?: NormalizedTerms;
  section_path?: SectionPath;
  source_page_number?: SourcePageNumber;
}
