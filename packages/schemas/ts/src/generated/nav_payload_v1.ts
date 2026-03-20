/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type Title = string;
export type SourcePageNumber = number;
export type Prev = string | null;
export type Next = string | null;
export type Pages = NavEntryV1[];

/**
 * Frontend navigation payload — ordered page list with prev/next links.
 */
export interface NavPayloadV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  pages?: Pages;
}
/**
 * A single page entry in the navigation payload.
 */
export interface NavEntryV1 {
  page_id: PageId;
  title?: Title;
  source_page_number?: SourcePageNumber;
  prev?: Prev;
  next?: Next;
}
