/* Auto-generated from JSON Schema — do not edit */

export type SchemaVersion = string;
export type DocumentId = string;
export type PageId = string;
export type ParagraphId = string;
export type Severity = 'info' | 'warning' | 'error' | 'critical';
export type Quote = string;
export type Why = string;
/**
 * @minItems 1
 */
export type Suggestions = [string, ...string[]];
export type Findings = TranslationStyleCriticFindingV1[];

/**
 * Style critic findings for one translated page.
 */
export interface TranslationStyleCriticPageV1 {
  schema_version?: SchemaVersion;
  document_id: DocumentId;
  page_id: PageId;
  findings?: Findings;
}
/**
 * A single paragraph-local Russian readability/style finding.
 */
export interface TranslationStyleCriticFindingV1 {
  paragraph_id: ParagraphId;
  severity: Severity;
  quote: Quote;
  why: Why;
  suggestions: Suggestions;
}
