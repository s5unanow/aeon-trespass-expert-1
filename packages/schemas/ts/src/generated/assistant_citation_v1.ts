/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type Edition = string;
export type PageId = string;
export type SourcePageNumber = number;
export type CanonicalAnchorId = string;
export type DeepLink = string;
export type QuoteSnippet = string;
export type RelevanceReason = string;

/**
 * Citation tying an assistant answer claim to a specific rule chunk.
 *
 * Each citation resolves to a reader deep link and includes a short
 * verbatim snippet from the rulebook for verification.
 */
export interface AssistantCitationV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  edition: Edition;
  page_id: PageId;
  source_page_number: SourcePageNumber;
  canonical_anchor_id: CanonicalAnchorId;
  deep_link?: DeepLink;
  quote_snippet?: QuoteSnippet;
  relevance_reason?: RelevanceReason;
}
